"""KnowledgeService text create / update helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.knowledge.files import document_path
from octop.infra.knowledge.service import KnowledgeService
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / ".octop"))
    paths = PathLayout.from_env()
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    owner_id = UserRepo(db).create(username="owner", password_hash="h", role="user")
    settings = MagicMock()
    settings.get.side_effect = lambda key, default=None: {
        "knowledge_feature_enabled": "1",
        "knowledge_embedding_backend": "onnx",
        "knowledge_embedding_model": "tiny",
    }.get(key, default)
    return SimpleNamespace(
        knowledge_repo=KnowledgeRepo(db),
        settings_repo=settings,
        provider_repo=None,
        owner_id=owner_id,
    )


def test_create_and_update_text_document(
    services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "octop.infra.knowledge.service.assert_knowledge_usable",
        lambda *_a, **_k: None,
    )
    svc = KnowledgeService(services)
    base = svc.create_base(owner_user_id=services.owner_id, name="Docs")
    created = svc.create_text_document(
        base.id,
        actor_user_id=services.owner_id,
        name="notes",
        format="md",
        content="# Hello\n",
    )
    assert created.filename == "notes.md"
    assert created.content_type == "text/markdown"
    assert created.status == "pending"
    path = document_path(base.id, created.id, created.filename)
    assert path.read_text(encoding="utf-8") == "# Hello\n"

    updated = svc.update_text_document(
        base.id,
        created.id,
        actor_user_id=services.owner_id,
        content="# Updated\n",
    )
    assert updated.status == "pending"
    assert path.read_text(encoding="utf-8") == "# Updated\n"
    raw = svc.read_text_document(base.id, created.id, actor_user_id=services.owner_id)
    assert raw["text"] == "# Updated\n"


def test_upload_spreadsheet_documents(
    services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "octop.infra.knowledge.service.assert_knowledge_usable",
        lambda *_a, **_k: None,
    )
    svc = KnowledgeService(services)
    base = svc.create_base(owner_user_id=services.owner_id, name="Sheets")
    xlsx = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="sales.xlsx",
        content_type="application/octet-stream",
        content=b"fake-xlsx",
    )
    csv_doc = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="sales.csv",
        content_type="application/vnd.ms-excel",
        content=b"a,b\n1,2\n",
    )
    xls = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="legacy.xls",
        content_type="application/vnd.ms-excel",
        content=b"fake-xls",
    )
    html = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="page.html",
        content_type="text/html",
        content=b"<p>hi</p>",
    )
    json_doc = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="data.json",
        content_type="application/json",
        content=b"{}",
    )
    xlsm = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="macro.xlsm",
        content_type="application/octet-stream",
        content=b"fake-xlsm",
    )
    assert xlsx.content_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert csv_doc.content_type == "text/csv"
    assert xls.content_type == "application/vnd.ms-excel"
    assert html.content_type == "text/html"
    assert json_doc.content_type == "application/json"
    assert xlsm.content_type == "application/vnd.ms-excel.sheet.macroEnabled.12"


def test_image_upload_requires_ocr(
    services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "octop.infra.knowledge.service.assert_knowledge_usable",
        lambda *_a, **_k: None,
    )
    svc = KnowledgeService(services)
    base = svc.create_base(owner_user_id=services.owner_id, name="Images")

    with pytest.raises(ValueError, match="OCR must be enabled"):
        svc.upload_document(
            base.id,
            actor_user_id=services.owner_id,
            filename="scan.png",
            content_type="image/png",
            content=b"image",
        )

    services.settings_repo.get.side_effect = lambda key, default=None: {
        "knowledge_feature_enabled": "1",
        "knowledge_embedding_backend": "onnx",
        "knowledge_embedding_model": "tiny",
        "knowledge_ocr_enabled": "true",
    }.get(key, default)
    created = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="scan.png",
        content_type="application/octet-stream",
        content=b"image",
    )
    assert created.content_type == "image/png"


def test_update_text_document_rename(
    services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "octop.infra.knowledge.service.assert_knowledge_usable",
        lambda *_a, **_k: None,
    )
    svc = KnowledgeService(services)
    base = svc.create_base(owner_user_id=services.owner_id, name="Docs")
    created = svc.create_text_document(
        base.id,
        actor_user_id=services.owner_id,
        name="notes",
        format="md",
        content="# Hello\n",
    )
    assert created.filename == "notes.md"
    old_path = document_path(base.id, created.id, created.filename)
    assert old_path.exists()

    # Rename with extension automatically appended if omitted
    updated = svc.update_text_document(
        base.id,
        created.id,
        actor_user_id=services.owner_id,
        content="# Renamed Hello\n",
        name="renamed_notes",
    )
    assert updated.filename == "renamed_notes.md"
    assert updated.status == "pending"
    new_path = document_path(base.id, created.id, updated.filename)
    assert new_path.exists()
    assert new_path.read_text(encoding="utf-8") == "# Renamed Hello\n"

    # Rename with full extension specified
    updated2 = svc.update_text_document(
        base.id,
        created.id,
        actor_user_id=services.owner_id,
        content="# Final Hello\n",
        name="final_notes.md",
    )
    assert updated2.filename == "final_notes.md"
    final_path = document_path(base.id, created.id, updated2.filename)
    assert final_path.exists()
    assert final_path.read_text(encoding="utf-8") == "# Final Hello\n"

    # Saving with the current name still writes content and keeps the name.
    updated3 = svc.update_text_document(
        base.id,
        created.id,
        actor_user_id=services.owner_id,
        content="# Same name\n",
        name="final_notes.md",
    )
    assert updated3.filename == "final_notes.md"
    assert final_path.read_text(encoding="utf-8") == "# Same name\n"


def test_rename_document_preserves_original_suffix(
    services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "octop.infra.knowledge.service.assert_knowledge_usable",
        lambda *_a, **_k: None,
    )
    svc = KnowledgeService(services)
    base = svc.create_base(owner_user_id=services.owner_id, name="Docs")
    created = svc.create_text_document(
        base.id,
        actor_user_id=services.owner_id,
        name="intro",
        format="md",
        content="welcome\n",
    )
    assert created.filename == "intro.md"
    orig_path = document_path(base.id, created.id, created.filename)
    assert orig_path.exists()

    # Omitted extension: the original suffix is appended.
    renamed = svc.rename_document(
        base.id,
        created.id,
        new_name="overview",
        actor_user_id=services.owner_id,
    )
    assert renamed.filename == "overview.md"
    new_path = document_path(base.id, created.id, renamed.filename)
    # Storage is keyed by document id plus suffix, so the bytes never move.
    assert new_path == orig_path
    assert new_path.read_text(encoding="utf-8") == "welcome\n"

    # A different extension never changes the stored format.
    renamed = svc.rename_document(
        base.id,
        created.id,
        new_name="overview.txt",
        actor_user_id=services.owner_id,
    )
    assert renamed.filename == "overview.md"

    # Dots that belong to a human name are not treated as an extension.
    renamed = svc.rename_document(
        base.id,
        created.id,
        new_name="v1.2 notes",
        actor_user_id=services.owner_id,
    )
    assert renamed.filename == "v1.2 notes.md"
    assert new_path.read_text(encoding="utf-8") == "welcome\n"
