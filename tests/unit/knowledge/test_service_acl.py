"""Unit tests for knowledge-base access control and document orchestration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.knowledge import service as service_module
from octop.infra.knowledge.service import MAX_DOCS_PER_KB, KnowledgeService
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> KnowledgeService:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    services = SimpleNamespace(
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
        paths=PathLayout.from_env(),
    )
    monkeypatch.setattr(service_module, "assert_knowledge_usable", lambda *_args: None)
    return KnowledgeService(services)


def test_create_base_allows_shared_with_default_open(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")

    kb = service.create_base(
        owner_user_id=owner,
        name="Docs",
        shared=True,
        default_open=True,
    )
    assert kb.shared is True
    assert kb.default_open is True


def test_update_base_allows_enabling_both_shared_and_default_open(
    service: KnowledgeService,
) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    kb = service.create_base(owner_user_id=owner, name="Docs", shared=False, default_open=True)

    updated = service.update_base(kb.id, actor_user_id=owner, shared=True)
    assert updated.shared is True
    assert updated.default_open is True


def test_shared_reader_cannot_upload(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    viewer = users.create(username="viewer", password_hash="h", role="user")
    kb = service._services.knowledge_repo.create_base(owner_user_id=owner, name="Docs", shared=True)

    with pytest.raises(PermissionError, match="write"):
        service.upload_document(
            kb.id,
            actor_user_id=viewer,
            filename="blocked.md",
            content_type="text/markdown",
            content=b"# blocked",
        )

    assert service.get_readable_base(kb.id, actor_user_id=viewer).id == kb.id
    doc = service.upload_document(
        kb.id,
        actor_user_id=owner,
        filename="allowed.md",
        content_type="text/markdown",
        content=b"# allowed",
    )
    assert doc.filename == "allowed.md"
    assert service._services.knowledge_repo.count_documents(kb.id) == 1
    assert service._services.knowledge_repo.get_base(kb.id).doc_count == 1

    service.delete_document(kb.id, doc.id, actor_user_id=owner)
    assert service._services.knowledge_repo.count_documents(kb.id) == 0
    assert service._services.knowledge_repo.get_base(kb.id).doc_count == 0


def test_shared_reader_can_preview_document_text(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    viewer = users.create(username="viewer", password_hash="h", role="user")
    kb = service._services.knowledge_repo.create_base(owner_user_id=owner, name="Docs", shared=True)
    doc = service.upload_document(
        kb.id,
        actor_user_id=owner,
        filename="notes.md",
        content_type="text/markdown",
        content=b"# Hello preview\n\nBody text.",
    )

    preview = service.preview_document(kb.id, doc.id, actor_user_id=viewer, is_admin=False)

    assert preview["id"] == doc.id
    assert preview["filename"] == "notes.md"
    assert "Hello preview" in preview["text"]
    assert "Body text." in preview["text"]


def test_create_base_enforces_owner_limit(service: KnowledgeService) -> None:
    from octop.infra.knowledge.service import MAX_BASES_PER_OWNER

    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    for ordinal in range(MAX_BASES_PER_OWNER):
        service.create_base(owner_user_id=owner, name=f"kb-{ordinal}")

    with pytest.raises(ValueError, match="knowledge bases"):
        service.create_base(owner_user_id=owner, name="one-too-many")


def test_upload_enforces_document_byte_limit(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    kb = service.create_base(owner_user_id=owner, name="Docs")
    service._services.config = SimpleNamespace(max_upload_bytes=1024, max_upload_mb=1)

    with pytest.raises(ValueError, match="document size"):
        service.upload_document(
            kb.id,
            actor_user_id=owner,
            filename="huge.md",
            content_type="text/markdown",
            content=b"x" * 1025,
        )


def test_delete_document_works_when_feature_disabled(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    kb = service.create_base(owner_user_id=owner, name="Docs")
    doc = service.upload_document(
        kb.id,
        actor_user_id=owner,
        filename="notes.md",
        content_type="text/markdown",
        content=b"# hi",
    )

    import octop.infra.knowledge.service as mod

    def deny(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("knowledge feature is disabled")

    original = mod.assert_knowledge_usable
    mod.assert_knowledge_usable = deny  # type: ignore[assignment]
    try:
        service.delete_document(kb.id, doc.id, actor_user_id=owner)
    finally:
        mod.assert_knowledge_usable = original

    assert service._services.knowledge_repo.get_document(doc.id) is None


def test_upload_enforces_document_limit(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    kb = service._services.knowledge_repo.create_base(owner_user_id=owner, name="Docs")
    for ordinal in range(MAX_DOCS_PER_KB):
        service._services.knowledge_repo.create_document(
            kb_id=kb.id,
            filename=f"{ordinal}.md",
            content_type="text/markdown",
            byte_size=1,
        )

    with pytest.raises(ValueError, match="100"):
        service.upload_document(
            kb.id,
            actor_user_id=owner,
            filename="one-too-many.md",
            content_type="text/markdown",
            content=b"x",
        )


def test_rename_folder_rewrites_descendant_paths(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    kb = service.create_base(owner_user_id=owner, name="Docs")
    folder = service.create_folder(kb.id, actor_user_id=owner, path="notes/law")
    doc = service.upload_document(
        kb.id,
        actor_user_id=owner,
        filename="act.md",
        content_type="text/markdown",
        content=b"x",
        path="notes/law/act.md",
    )

    renamed = service.rename_document(kb.id, folder.id, actor_user_id=owner, new_name="legal")
    assert renamed.path == "notes/legal"
    assert renamed.filename == "legal"
    assert service._services.knowledge_repo.get_document(doc.id).path == "notes/legal/act.md"


def test_rename_rejects_name_collision(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    kb = service.create_base(owner_user_id=owner, name="Docs")
    repo = service._services.knowledge_repo
    repo.ensure_folder(kb.id, "a")
    repo.ensure_folder(kb.id, "b")

    with pytest.raises(ValueError, match="already exists"):
        service.rename_document(
            kb.id,
            repo.get_document_by_path(kb.id, "a").id,
            actor_user_id=owner,
            new_name="b",
        )


def test_rename_rejects_name_with_separator(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    kb = service.create_base(owner_user_id=owner, name="Docs")
    folder = service.create_folder(kb.id, actor_user_id=owner, path="a")

    with pytest.raises(ValueError, match="invalid knowledge document name"):
        service.rename_document(kb.id, folder.id, actor_user_id=owner, new_name="b/c")


def test_rename_same_name_is_idempotent(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    kb = service.create_base(owner_user_id=owner, name="Docs")
    folder = service.create_folder(kb.id, actor_user_id=owner, path="a")

    result = service.rename_document(kb.id, folder.id, actor_user_id=owner, new_name="a")
    assert result.id == folder.id
    assert result.path == "a"
    assert service._services.knowledge_repo.list_documents(kb.id) == [result]


def test_shared_reader_cannot_rename(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    viewer = users.create(username="viewer", password_hash="h", role="user")
    kb = service._services.knowledge_repo.create_base(owner_user_id=owner, name="Docs", shared=True)
    folder = service._services.knowledge_repo.ensure_folder(kb.id, "a")

    with pytest.raises(PermissionError, match="write"):
        service.rename_document(kb.id, folder.id, actor_user_id=viewer, new_name="b")
