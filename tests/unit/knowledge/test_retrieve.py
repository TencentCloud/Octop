"""Unit tests for knowledge retrieval during a chat turn."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.knowledge import retrieve as retrieve_module
from octop.infra.knowledge.citations import CITATIONS_MARKER_PREFIX
from octop.infra.knowledge.index import KnowledgeIndex


def test_retrieve_context_filters_unreadable_knowledge_base(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    services = SimpleNamespace(
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
    )
    reader = services.user_repo.create(username="reader", password_hash="h", role="user")
    owner = services.user_repo.create(username="owner", password_hash="h", role="user")
    allowed = services.knowledge_repo.create_base(owner_user_id=reader, name="Allowed")
    hidden = services.knowledge_repo.create_base(owner_user_id=owner, name="Hidden")
    allowed_doc = services.knowledge_repo.create_document(
        kb_id=allowed.id,
        filename="allowed.md",
        content_type="text/markdown",
        byte_size=1,
        status="ready",
    )
    hidden_doc = services.knowledge_repo.create_document(
        kb_id=hidden.id,
        filename="hidden.md",
        content_type="text/markdown",
        byte_size=1,
        status="ready",
    )
    KnowledgeIndex(allowed.id).replace_doc_chunks(allowed_doc.id, ["allowed fact"], [[1.0, 0.0]])
    KnowledgeIndex(hidden.id).replace_doc_chunks(hidden_doc.id, ["secret fact"], [[1.0, 0.0]])
    services.settings_repo.set("knowledge_embedding_model", "test-model")
    monkeypatch.setattr(retrieve_module, "assert_knowledge_usable", lambda *_args: None)
    monkeypatch.setattr(
        retrieve_module, "embed_knowledge_texts", lambda _services, _texts: [[1.0, 0.0]]
    )

    context = asyncio.run(
        retrieve_module.retrieve_context(
            services,
            user_id=reader,
            is_admin=False,
            query="What facts are available?",
            knowledge_base_ids=[allowed.id, hidden.id],
        )
    )

    assert "allowed fact" in context
    assert "allowed.md" in context
    assert CITATIONS_MARKER_PREFIX in context
    assert "secret fact" not in context
    assert "hidden.md" not in context


def test_retrieve_context_skips_empty_non_text_turn() -> None:
    context = asyncio.run(
        retrieve_module.retrieve_context(
            SimpleNamespace(),
            user_id=1,
            is_admin=False,
            query=None,  # type: ignore[arg-type]
            knowledge_base_ids=["kb-1"],
        )
    )

    assert context == ""


@pytest.mark.parametrize("status", ["pending", "processing", "failed", "deleted"])
def test_unavailable_chunks_do_not_displace_ready_top_k(tmp_path, monkeypatch, status) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    services = SimpleNamespace(
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
    )
    owner = services.user_repo.create(username="owner", password_hash="h", role="user")
    base = services.knowledge_repo.create_base(owner_user_id=owner, name="Facts")
    ready = services.knowledge_repo.create_document(
        kb_id=base.id,
        filename="ready.md",
        content_type="text/markdown",
        byte_size=1,
        status="ready",
    )
    stale = services.knowledge_repo.create_document(
        kb_id=base.id,
        filename="stale.md",
        content_type="text/markdown",
        byte_size=1,
        status="ready" if status == "deleted" else status,
    )
    index = KnowledgeIndex(base.id)
    index.replace_doc_chunks(
        ready.id, ["usable fact", "lower ranked fact"], [[0.8, 0.2], [0.0, 1.0]]
    )
    index.replace_doc_chunks(stale.id, ["stale fact"] * 8, [[1.0, 0.0]] * 8)
    if status == "deleted":
        services.knowledge_repo.delete_document(stale.id)
    monkeypatch.setattr(retrieve_module, "assert_knowledge_usable", lambda *_args: None)
    monkeypatch.setattr(
        retrieve_module, "embed_knowledge_texts", lambda _services, _texts: [[1.0, 0.0]]
    )

    context = asyncio.run(
        retrieve_module.retrieve_context(
            services,
            user_id=owner,
            is_admin=False,
            query="fact",
            knowledge_base_ids=[base.id],
            k=1,
        )
    )

    assert "usable fact" in context
    assert "ready.md" in context
    assert "stale fact" not in context
    assert "stale.md" not in context
    assert "lower ranked fact" not in context
