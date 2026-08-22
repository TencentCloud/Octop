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
