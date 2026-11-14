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
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge import service as service_module
from octop.infra.knowledge.index import KnowledgeIndex
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


def test_update_base_validates_max_documents_range(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="ow", password_hash="h", role="user")
    kb = service.create_base(owner_user_id=owner, name="Docs")
    # In range
    service.update_base(kb.id, actor_user_id=owner, max_documents=0)
    assert service.get_readable_base(kb.id, actor_user_id=owner).max_documents == 0
    service.update_base(kb.id, actor_user_id=owner, max_documents=500)
    assert service.get_readable_base(kb.id, actor_user_id=owner).max_documents == 500
    service.update_base(kb.id, actor_user_id=owner, max_documents=10_000)
    assert service.get_readable_base(kb.id, actor_user_id=owner).max_documents == 10_000
    # Out of range
    with pytest.raises(ValueError, match="max_documents must be between"):
        service.update_base(kb.id, actor_user_id=owner, max_documents=-1)
    with pytest.raises(ValueError, match="max_documents must be between"):
        service.update_base(kb.id, actor_user_id=owner, max_documents=10_001)
    # Omit keeps value
    service.update_base(kb.id, actor_user_id=owner, description="keep")
    assert service.get_readable_base(kb.id, actor_user_id=owner).max_documents == 10_000


def _base_with_tree(service: KnowledgeService) -> tuple[int, str]:
    """owner id and a base holding ``notes/law/act.md``, ``notes/readme.md`` and ``archive``."""
    owner = service._services.user_repo.create(username="owner", password_hash="h", role="user")
    kb = service.create_base(owner_user_id=owner, name="Docs")
    for path in ("notes/law/act.md", "notes/readme.md"):
        service.upload_document(
            kb.id,
            actor_user_id=owner,
            filename=path.rsplit("/", 1)[-1],
            content_type="text/markdown",
            content=b"x",
            path=path,
        )
    service.create_folder(kb.id, actor_user_id=owner, path="archive")
    return owner, kb.id


def test_move_file_into_another_folder_and_back_to_root(service: KnowledgeService) -> None:
    owner, kb_id = _base_with_tree(service)
    repo = service._services.knowledge_repo
    doc = repo.get_document_by_path(kb_id, "notes/readme.md")

    moved = service.move_document(kb_id, doc.id, actor_user_id=owner, target_folder="archive")
    assert (moved.id, moved.path, moved.filename) == (doc.id, "archive/readme.md", "readme.md")
    assert repo.get_document_by_path(kb_id, "notes/readme.md") is None

    at_root = service.move_document(kb_id, doc.id, actor_user_id=owner, target_folder="")
    assert at_root.path == "readme.md"


def test_move_folder_takes_its_subtree(service: KnowledgeService) -> None:
    owner, kb_id = _base_with_tree(service)
    repo = service._services.knowledge_repo
    folder = repo.get_document_by_path(kb_id, "notes")

    moved = service.move_document(kb_id, folder.id, actor_user_id=owner, target_folder="/archive/")

    assert moved.path == "archive/notes"
    assert sorted(document.path for document in repo.list_documents(kb_id)) == [
        "archive",
        "archive/notes",
        "archive/notes/law",
        "archive/notes/law/act.md",
        "archive/notes/readme.md",
    ]


def test_move_keeps_a_sibling_whose_name_shares_the_prefix(service: KnowledgeService) -> None:
    owner, kb_id = _base_with_tree(service)
    repo = service._services.knowledge_repo
    repo.ensure_folder(kb_id, "notes-old")

    service.move_document(
        kb_id,
        repo.get_document_by_path(kb_id, "notes").id,
        actor_user_id=owner,
        target_folder="archive",
    )

    assert repo.get_document_by_path(kb_id, "notes-old") is not None


@pytest.mark.parametrize("target", ["notes", "notes/law"])
def test_move_folder_into_itself_is_rejected(service: KnowledgeService, target: str) -> None:
    owner, kb_id = _base_with_tree(service)
    folder = service._services.knowledge_repo.get_document_by_path(kb_id, "notes")

    with pytest.raises(OctopError) as raised:
        service.move_document(kb_id, folder.id, actor_user_id=owner, target_folder=target)

    assert raised.value.code is ErrorCode.KNOWLEDGE_MOVE_INVALID


def test_move_rejects_a_name_collision_in_the_target(service: KnowledgeService) -> None:
    owner, kb_id = _base_with_tree(service)
    repo = service._services.knowledge_repo
    service.upload_document(
        kb_id,
        actor_user_id=owner,
        filename="readme.md",
        content_type="text/markdown",
        content=b"y",
        path="archive/readme.md",
    )

    with pytest.raises(OctopError) as raised:
        service.move_document(
            kb_id,
            repo.get_document_by_path(kb_id, "notes/readme.md").id,
            actor_user_id=owner,
            target_folder="archive",
        )

    assert raised.value.code is ErrorCode.KNOWLEDGE_MOVE_NAME_TAKEN
    assert repo.get_document_by_path(kb_id, "notes/readme.md") is not None


@pytest.mark.parametrize("target", ["missing", "notes/readme.md", "../outside"])
def test_move_needs_an_existing_folder(service: KnowledgeService, target: str) -> None:
    owner, kb_id = _base_with_tree(service)
    doc = service._services.knowledge_repo.get_document_by_path(kb_id, "notes/law/act.md")

    with pytest.raises(LookupError, match="folder not found"):
        service.move_document(kb_id, doc.id, actor_user_id=owner, target_folder=target)


def test_move_to_the_current_folder_changes_nothing(service: KnowledgeService) -> None:
    owner, kb_id = _base_with_tree(service)
    repo = service._services.knowledge_repo
    doc = repo.get_document_by_path(kb_id, "notes/readme.md")

    same = service.move_document(kb_id, doc.id, actor_user_id=owner, target_folder="notes")

    assert same.updated_at == doc.updated_at
    assert same.path == "notes/readme.md"


def test_move_does_not_cross_knowledge_bases(service: KnowledgeService) -> None:
    owner, kb_id = _base_with_tree(service)
    other = service.create_base(owner_user_id=owner, name="Other")
    doc = service._services.knowledge_repo.get_document_by_path(kb_id, "notes/readme.md")

    with pytest.raises(LookupError, match="document not found"):
        service.move_document(other.id, doc.id, actor_user_id=owner, target_folder="")


def _two_bases(service: KnowledgeService) -> tuple[int, str, str]:
    """owner, a source base holding ``notes/law/act.md`` and ``notes/readme.md``, and an
    empty target base with an ``inbox`` folder. Every file is indexed with one chunk."""
    owner, kb_id = _base_with_tree(service)
    repo = service._services.knowledge_repo
    for row in repo.list_documents(kb_id):
        if not row.is_dir:
            KnowledgeIndex(kb_id).replace_doc_chunks(row.id, [f"text of {row.path}"], [[1.0, 0.0]])
            repo.update_document(row.id, status="ready", chunk_count=1)
    repo.update_base(kb_id, embedding_dim=2)
    target = service.create_base(owner_user_id=owner, name="Target")
    service.create_folder(target.id, actor_user_id=owner, path="inbox")
    return owner, kb_id, target.id


def test_move_file_to_another_base_takes_its_original_and_chunks(
    service: KnowledgeService,
) -> None:
    owner, kb_id, target_id = _two_bases(service)
    repo = service._services.knowledge_repo
    doc = repo.get_document_by_path(kb_id, "notes/readme.md")

    moved = service.move_document(
        kb_id, doc.id, actor_user_id=owner, target_folder="inbox", target_kb_id=target_id
    )

    assert (moved.id, moved.kb_id, moved.path) == (doc.id, target_id, "inbox/readme.md")
    assert (moved.status, moved.chunk_count) == ("ready", 1)
    assert repo.get_document_by_path(kb_id, "notes/readme.md") is None
    assert (repo.get_base(kb_id).doc_count, repo.get_base(target_id).doc_count) == (1, 1)
    assert repo.get_base(target_id).embedding_dim == 2
    blobs = service._blobs()
    assert blobs.read_bytes(target_id, doc.id, "readme.md") == b"x"
    assert not blobs.exists(kb_id, doc.id, "readme.md")
    assert KnowledgeIndex(target_id).read_doc_chunks(doc.id) == [
        ("text of notes/readme.md", [1.0, 0.0], {})
    ]
    assert KnowledgeIndex(kb_id).list_doc_chunks(doc.id) == []


def test_move_folder_to_another_base_takes_its_subtree(service: KnowledgeService) -> None:
    owner, kb_id, target_id = _two_bases(service)
    repo = service._services.knowledge_repo
    folder = repo.get_document_by_path(kb_id, "notes")

    service.move_document(
        kb_id, folder.id, actor_user_id=owner, target_folder="", target_kb_id=target_id
    )

    assert repo.list_documents(kb_id) == [repo.get_document_by_path(kb_id, "archive")]
    assert sorted(row.path for row in repo.list_documents(target_id)) == [
        "inbox",
        "notes",
        "notes/law",
        "notes/law/act.md",
        "notes/readme.md",
    ]
    act = repo.get_document_by_path(target_id, "notes/law/act.md")
    assert KnowledgeIndex(target_id).list_doc_chunks(act.id) == [(0, "text of notes/law/act.md")]
    assert (repo.get_base(kb_id).doc_count, repo.get_base(target_id).doc_count) == (0, 2)


def test_move_to_a_base_with_another_model_indexes_again(service: KnowledgeService) -> None:
    owner, kb_id, target_id = _two_bases(service)
    repo = service._services.knowledge_repo
    repo.update_base(target_id, embedding_model="other-model")
    doc = repo.get_document_by_path(kb_id, "notes/readme.md")

    moved = service.move_document(
        kb_id, doc.id, actor_user_id=owner, target_folder="", target_kb_id=target_id
    )

    assert (moved.status, moved.chunk_count) == ("pending", 0)
    assert service.pending_file_ids(moved) == [doc.id]
    assert KnowledgeIndex(target_id).list_doc_chunks(doc.id) == []
    assert KnowledgeIndex(kb_id).list_doc_chunks(doc.id) == []
    assert service._blobs().exists(target_id, doc.id, "readme.md")


def test_move_to_another_base_keeps_a_failed_file_failed(service: KnowledgeService) -> None:
    owner, kb_id, target_id = _two_bases(service)
    repo = service._services.knowledge_repo
    doc = repo.get_document_by_path(kb_id, "notes/readme.md")
    repo.update_document(doc.id, status="failed", error_message="bad file", chunk_count=0)

    moved = service.move_document(
        kb_id, doc.id, actor_user_id=owner, target_folder="", target_kb_id=target_id
    )

    assert (moved.status, moved.error_message) == ("failed", "bad file")


def test_move_to_another_base_waits_for_indexing(service: KnowledgeService) -> None:
    owner, kb_id, target_id = _two_bases(service)
    repo = service._services.knowledge_repo
    repo.update_document(
        repo.get_document_by_path(kb_id, "notes/law/act.md").id, status="processing"
    )

    with pytest.raises(OctopError) as raised:
        service.move_document(
            kb_id,
            repo.get_document_by_path(kb_id, "notes").id,
            actor_user_id=owner,
            target_folder="",
            target_kb_id=target_id,
        )

    assert raised.value.code is ErrorCode.KNOWLEDGE_MOVE_BUSY
    assert repo.get_document_by_path(kb_id, "notes/law/act.md") is not None


def test_move_to_a_full_base_changes_nothing(service: KnowledgeService) -> None:
    owner, kb_id, target_id = _two_bases(service)
    repo = service._services.knowledge_repo
    service.update_base(target_id, actor_user_id=owner, max_documents=1)
    folder = repo.get_document_by_path(kb_id, "notes")

    with pytest.raises(OctopError) as raised:
        service.move_document(
            kb_id, folder.id, actor_user_id=owner, target_folder="", target_kb_id=target_id
        )

    assert raised.value.code is ErrorCode.KNOWLEDGE_DOC_LIMIT
    assert repo.get_document(folder.id).kb_id == kb_id
    assert repo.get_base(target_id).doc_count == 0
    assert repo.get_base(kb_id).doc_count == 2


def test_move_to_another_base_rejects_a_name_collision(service: KnowledgeService) -> None:
    owner, kb_id, target_id = _two_bases(service)
    repo = service._services.knowledge_repo
    service.create_folder(target_id, actor_user_id=owner, path="notes")

    with pytest.raises(OctopError) as raised:
        service.move_document(
            kb_id,
            repo.get_document_by_path(kb_id, "notes").id,
            actor_user_id=owner,
            target_folder="",
            target_kb_id=target_id,
        )

    assert raised.value.code is ErrorCode.KNOWLEDGE_MOVE_NAME_TAKEN


def test_move_to_another_base_needs_its_folder(service: KnowledgeService) -> None:
    owner, kb_id, target_id = _two_bases(service)
    doc = service._services.knowledge_repo.get_document_by_path(kb_id, "notes/readme.md")

    with pytest.raises(LookupError, match="folder not found"):
        service.move_document(
            kb_id, doc.id, actor_user_id=owner, target_folder="archive", target_kb_id=target_id
        )


def test_move_into_a_base_the_actor_cannot_write_is_rejected(service: KnowledgeService) -> None:
    owner, kb_id, _target_id = _two_bases(service)
    stranger = service._services.user_repo.create(username="s", password_hash="h", role="user")
    theirs = service._services.knowledge_repo.create_base(
        owner_user_id=stranger, name="Theirs", shared=True
    )
    doc = service._services.knowledge_repo.get_document_by_path(kb_id, "notes/readme.md")

    with pytest.raises(PermissionError, match="write"):
        service.move_document(
            kb_id, doc.id, actor_user_id=owner, target_folder="", target_kb_id=theirs.id
        )


def test_shared_reader_cannot_move(service: KnowledgeService) -> None:
    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    viewer = users.create(username="viewer", password_hash="h", role="user")
    repo = service._services.knowledge_repo
    kb = repo.create_base(owner_user_id=owner, name="Docs", shared=True)
    folder = repo.ensure_folder(kb.id, "a")
    repo.ensure_folder(kb.id, "b")

    with pytest.raises(PermissionError, match="write"):
        service.move_document(kb.id, folder.id, actor_user_id=viewer, target_folder="b")


def _graph_fixture(service: KnowledgeService) -> tuple[str, int, int, str]:
    from octop.infra.knowledge.graph_store import (
        ChunkEntity,
        ChunkGraph,
        ChunkRelation,
        SqliteKnowledgeGraphStore,
    )
    from octop.infra.knowledge.index import KnowledgeIndex

    users = service._services.user_repo
    owner = users.create(username="owner", password_hash="h", role="user")
    reader = users.create(username="reader", password_hash="h", role="user")
    kb = service.create_base(owner_user_id=owner, name="Docs", shared=True)
    document = service._repo.create_document(
        kb_id=kb.id, filename="plan.md", content_type="text/markdown", byte_size=1, status="ready"
    )
    service._repo.create_document(
        kb_id=kb.id, filename="draft.md", content_type="text/markdown", byte_size=1
    )
    KnowledgeIndex(kb.id).replace_doc_chunks(document.id, ["Alice leads Apollo."], [[1.0, 0.0]])
    SqliteKnowledgeGraphStore(kb.id).replace_document(
        document.id,
        [
            ChunkGraph(
                ordinal=0,
                entities=(ChunkEntity("Alice", "person"), ChunkEntity("Apollo", "product")),
                relations=(ChunkRelation("Alice", "Apollo", "leads"),),
            )
        ],
    )
    return kb.id, owner, reader, document.id


def test_readers_can_view_a_graph_but_not_build_or_delete_it(service: KnowledgeService) -> None:
    kb_id, owner, reader, doc_id = _graph_fixture(service)
    outsider = service._services.user_repo.create(username="out", password_hash="h", role="user")
    service.update_base(kb_id, actor_user_id=owner, shared=False)
    with pytest.raises(PermissionError):
        service.get_graph(kb_id, actor_user_id=outsider)
    service.update_base(kb_id, actor_user_id=owner, shared=True)

    view = service.get_graph(kb_id, actor_user_id=reader)

    assert view["stats"]["built"] is True
    assert view["stats"]["documents_total"] == 1
    assert [node["name"] for node in view["nodes"]] == ["Alice", "Apollo"]
    assert view["edges"][0]["labels"] == ["leads"]
    entity = service.get_graph_entity(kb_id, "alice", actor_user_id=reader)
    assert entity["passages"][0]["doc_id"] == doc_id
    with pytest.raises(PermissionError):
        service.graph_build_targets(kb_id, actor_user_id=reader)
    with pytest.raises(PermissionError):
        service.clear_graph(kb_id, actor_user_id=reader)


def test_graph_build_needs_an_extraction_model_and_targets_indexed_documents(
    service: KnowledgeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb_id, owner, _reader, doc_id = _graph_fixture(service)

    with pytest.raises(RuntimeError, match="knowledge graph extraction is not ready"):
        service.graph_build_targets(kb_id, actor_user_id=owner)

    monkeypatch.setattr(service_module, "get_graph_capability", lambda *_args: {"usable": True})
    assert service.graph_build_targets(kb_id, actor_user_id=owner) == [doc_id]


def test_clearing_a_graph_and_deleting_a_document_remove_graph_rows(
    service: KnowledgeService,
) -> None:
    from octop.infra.knowledge.graph_store import SqliteKnowledgeGraphStore

    kb_id, owner, _reader, doc_id = _graph_fixture(service)
    store = SqliteKnowledgeGraphStore(kb_id)

    service.delete_document(kb_id, doc_id, actor_user_id=owner)
    assert store.counts() == (0, 0)
    assert store.document_states() == {}

    store.mark_document("other", "ready")
    service.clear_graph(kb_id, actor_user_id=owner)
    assert service.get_graph(kb_id, actor_user_id=owner)["stats"]["built"] is False
