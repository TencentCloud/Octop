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
from octop.infra.knowledge.graph_store import (
    ChunkEntity,
    ChunkGraph,
    ChunkRelation,
    SqliteKnowledgeGraphStore,
)
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


def test_format_context_cites_only_documents_inside_the_budget() -> None:
    base = SimpleNamespace(id="kb", name="KB")
    doc_a = SimpleNamespace(id="a", filename="a.md", path="a.md")
    doc_b = SimpleNamespace(id="b", filename="b.md", path="b.md")
    hit_a = SimpleNamespace(text="alpha " * 40, ordinal=0)
    hit_b = SimpleNamespace(text="beta " * 40, ordinal=0)

    text = retrieve_module._format_context(
        [(base, hit_a, doc_a), (base, hit_b, doc_b)],
        char_budget=80,
        locale="en",
    )

    marker = text.split(CITATIONS_MARKER_PREFIX, 1)[1]
    assert "a.md" in marker
    assert "b.md" not in marker


def _graph_services(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    services = SimpleNamespace(
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
    )
    owner = services.user_repo.create(username="owner", password_hash="h", role="user")
    base = services.knowledge_repo.create_base(owner_user_id=owner, name="Docs")
    document = services.knowledge_repo.create_document(
        kb_id=base.id,
        filename="plan.md",
        content_type="text/markdown",
        byte_size=1,
        status="ready",
    )
    # Four passages rank by similarity; the fifth is unrelated by wording.
    texts = ["Apollo overview", "Apollo timeline", "Apollo risks", "Apollo team", "Budget rules"]
    vectors = [[1.0, 0.0], [0.9, 0.1], [0.8, 0.2], [0.7, 0.3], [0.0, 1.0]]
    KnowledgeIndex(base.id).replace_doc_chunks(document.id, texts, vectors)
    SqliteKnowledgeGraphStore(base.id).replace_document(
        document.id,
        [
            ChunkGraph(
                ordinal=4,
                entities=(ChunkEntity("Apollo"), ChunkEntity("Finance Board")),
                relations=(
                    ChunkRelation(
                        "Apollo", "Finance Board", "is funded by", "The board signs off.", 9
                    ),
                ),
            )
        ],
    )
    monkeypatch.setattr(retrieve_module, "assert_knowledge_usable", lambda *_args: None)
    monkeypatch.setattr(
        retrieve_module, "embed_knowledge_texts", lambda _services, _texts: [[1.0, 0.0]]
    )
    return services, owner, base


def _retrieve(services, owner, base, **kwargs):  # type: ignore[no-untyped-def]
    return asyncio.run(
        retrieve_module.retrieve_context(
            services,
            user_id=owner,
            is_admin=False,
            query="Who funds Apollo?",
            knowledge_base_ids=[base.id],
            **kwargs,
        )
    )


def test_retrieve_context_adds_graph_passage_and_relations(tmp_path, monkeypatch) -> None:
    services, owner, base = _graph_services(tmp_path, monkeypatch)
    services.settings_repo.set("knowledge_graph_enabled", "true")

    context = _retrieve(services, owner, base, k=4)

    # The linked passage takes the last of four slots; the weakest vector hit gives way.
    assert "Budget rules" in context
    assert "Apollo team" not in context
    assert context.index("Apollo overview") < context.index("Budget rules")
    assert "- Apollo -> is funded by -> Finance Board: The board signs off." in context
    assert context.index("Budget rules") < context.index("- Apollo -> is funded by")
    assert context.rstrip().endswith("-->")


def test_retrieve_context_ignores_the_graph_when_the_feature_is_off(tmp_path, monkeypatch) -> None:
    services, owner, base = _graph_services(tmp_path, monkeypatch)

    context = _retrieve(services, owner, base, k=4)

    assert "Apollo team" in context
    assert "Budget rules" not in context
    assert "is funded by" not in context


def test_retrieve_context_small_k_keeps_vector_passages(tmp_path, monkeypatch) -> None:
    services, owner, base = _graph_services(tmp_path, monkeypatch)
    services.settings_repo.set("knowledge_graph_enabled", "true")

    context = _retrieve(services, owner, base, k=2)

    assert "Apollo overview" in context and "Apollo timeline" in context
    assert "Budget rules" not in context
    assert "is funded by" in context


def test_retrieve_context_survives_a_broken_graph(tmp_path, monkeypatch) -> None:
    services, owner, base = _graph_services(tmp_path, monkeypatch)
    services.settings_repo.set("knowledge_graph_enabled", "true")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("graph storage is unavailable")

    monkeypatch.setattr(retrieve_module, "expand_query", boom)

    context = _retrieve(services, owner, base, k=4)

    assert "Apollo team" in context
    assert "is funded by" not in context
