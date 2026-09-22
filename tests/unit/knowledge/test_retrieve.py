"""Unit tests for knowledge retrieval during a chat turn."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

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


def test_retrieve_context_does_not_cite_documents_dropped_by_the_budget(
    tmp_path, monkeypatch
) -> None:
    """A hit cut off by ``char_budget`` must not appear in the dashboard citation marker.

    The marker is parsed by the dashboard and shown as sources, so citing a document whose text
    never reached the body points users at something the model did not see.
    """
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    services = SimpleNamespace(
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
    )
    reader = services.user_repo.create(username="reader", password_hash="h", role="user")
    first = services.knowledge_repo.create_base(owner_user_id=reader, name="First")
    second = services.knowledge_repo.create_base(owner_user_id=reader, name="Second")
    doc_a = services.knowledge_repo.create_document(
        kb_id=first.id,
        filename="first.md",
        content_type="text/markdown",
        byte_size=1,
        status="ready",
    )
    doc_b = services.knowledge_repo.create_document(
        kb_id=second.id,
        filename="second.md",
        content_type="text/markdown",
        byte_size=1,
        status="ready",
    )
    # The first hit fills the whole budget, so the second one is dropped before its text is used.
    KnowledgeIndex(first.id).replace_doc_chunks(doc_a.id, ["alpha " * 40], [[1.0, 0.0]])
    KnowledgeIndex(second.id).replace_doc_chunks(doc_b.id, ["beta fact"], [[1.0, 0.0]])
    services.settings_repo.set("knowledge_embedding_model", "test-model")
    monkeypatch.setattr(retrieve_module, "assert_knowledge_usable", lambda *_args: None)
    monkeypatch.setattr(
        retrieve_module, "embed_knowledge_texts", lambda _services, _texts: [[1.0, 0.0]]
    )

    out = asyncio.run(
        retrieve_module.retrieve_context(
            services,
            user_id=reader,
            is_admin=False,
            query="alpha",
            knowledge_base_ids=[first.id, second.id],
            k=2,
            char_budget=60,
            locale="zh",
            visible_bases=None,
        )
    )

    body, _, marker = out.partition(CITATIONS_MARKER_PREFIX)
    assert "alpha" in body
    assert "beta fact" not in body
    # The marker carries document metadata (filename), not the excerpt text.
    assert "second.md" not in marker
