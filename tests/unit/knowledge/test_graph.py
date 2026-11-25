"""Unit tests for building a knowledge graph and using it at retrieval time."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.knowledge import graph
from octop.infra.knowledge.graph_store import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_READY,
    ChunkEntity,
    ChunkGraph,
    ChunkRelation,
    SqliteKnowledgeGraphStore,
)
from octop.infra.knowledge.index import KnowledgeIndex


def _graph(ordinal: int, relations: list[tuple[str, str, str, str, float]]) -> ChunkGraph:
    names = dict.fromkeys(end for source, target, *_ in relations for end in (source, target))
    return ChunkGraph(
        ordinal=ordinal,
        entities=tuple(ChunkEntity(name, "concept", f"About {name}.") for name in names),
        relations=tuple(ChunkRelation(*relation) for relation in relations),
    )


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    repo = KnowledgeRepo(pool)
    owner = UserRepo(pool).create(username="owner", password_hash="h", role="user")
    base = repo.create_base(owner_user_id=owner, name="Docs")
    services = SimpleNamespace(
        knowledge_repo=repo,
        settings_repo=SettingsRepo(pool),
        provider_repo=SimpleNamespace(get=lambda _id: None),
    )
    return SimpleNamespace(services=services, repo=repo, kb_id=base.id, owner=owner)


def _document(env: SimpleNamespace, name: str, chunks: list[str], *, status: str = "ready") -> str:
    document = env.repo.create_document(
        kb_id=env.kb_id, filename=name, content_type="text/markdown", byte_size=1, status=status
    )
    KnowledgeIndex(env.kb_id).replace_doc_chunks(document.id, chunks, [[1.0, 0.0] for _ in chunks])
    return str(document.id)


def test_build_extracts_every_chunk_and_marks_the_document_ready(env: SimpleNamespace) -> None:
    doc_id = _document(env, "plan.md", ["Alice leads Apollo.", "Apollo ships in May."])
    calls: list[tuple[str, int, str]] = []

    def extractor(*, filename: str, ordinal: int, text: str) -> ChunkGraph:
        calls.append((filename, ordinal, text))
        return _graph(ordinal, [("Alice", "Apollo", "leads", text, 8)])

    graph.build_document_graph(env.services, env.kb_id, doc_id, extractor=extractor)

    store = SqliteKnowledgeGraphStore(env.kb_id)
    assert sorted(calls) == [
        ("plan.md", 0, "Alice leads Apollo."),
        ("plan.md", 1, "Apollo ships in May."),
    ]
    assert store.counts() == (2, 1)
    assert store.document_states()[doc_id].status == STATUS_READY
    assert store.relations_of(["alice"])[0].weight == 16


def test_build_keeps_what_it_could_extract_and_notes_the_rest(env: SimpleNamespace) -> None:
    doc_id = _document(env, "plan.md", ["good", "bad"])

    def extractor(*, filename: str, ordinal: int, text: str) -> ChunkGraph:
        if text == "bad":
            raise ValueError("knowledge graph extraction returned invalid JSON")
        return _graph(ordinal, [("Alice", "Apollo", "leads", "", 8)])

    graph.build_document_graph(env.services, env.kb_id, doc_id, extractor=extractor)

    state = SqliteKnowledgeGraphStore(env.kb_id).document_states()[doc_id]
    assert state.status == STATUS_READY
    assert state.error == "1 of 2 passages could not be extracted"


def test_build_fails_the_document_when_no_passage_could_be_extracted(
    env: SimpleNamespace,
) -> None:
    doc_id = _document(env, "plan.md", ["one", "two"])

    def extractor(**_kwargs: object) -> ChunkGraph:
        raise RuntimeError("provider is down")

    with pytest.raises(RuntimeError, match="failed for every passage"):
        graph.build_document_graph(env.services, env.kb_id, doc_id, extractor=extractor)

    state = SqliteKnowledgeGraphStore(env.kb_id).document_states()[doc_id]
    assert state.status == STATUS_FAILED
    assert "every passage" in state.error


def test_build_without_an_extraction_model_fails_the_document(env: SimpleNamespace) -> None:
    doc_id = _document(env, "plan.md", ["one"])

    with pytest.raises(RuntimeError, match="knowledge graph extraction is not ready"):
        graph.build_document_graph(env.services, env.kb_id, doc_id)

    assert SqliteKnowledgeGraphStore(env.kb_id).document_states()[doc_id].status == STATUS_FAILED


def test_build_forgets_a_document_that_no_longer_exists(env: SimpleNamespace) -> None:
    store = SqliteKnowledgeGraphStore(env.kb_id)
    store.replace_document("gone", [_graph(0, [("Alice", "Apollo", "leads", "", 8)])])

    graph.build_document_graph(env.services, env.kb_id, "gone", extractor=lambda **_: None)

    assert store.document_states() == {}
    assert store.counts() == (0, 0)


def test_reindexing_leaves_knowledge_bases_without_a_graph_alone(env: SimpleNamespace) -> None:
    doc_id = _document(env, "plan.md", ["one"])

    assert graph.mark_document_reindexed(env.services, env.kb_id, doc_id) is False
    assert not SqliteKnowledgeGraphStore(env.kb_id).path.exists()


def test_reindexing_drops_stale_rows_and_waits_when_extraction_is_unavailable(
    env: SimpleNamespace,
) -> None:
    doc_id = _document(env, "plan.md", ["one"])
    store = SqliteKnowledgeGraphStore(env.kb_id)
    store.replace_document(doc_id, [_graph(0, [("Alice", "Apollo", "leads", "", 8)])])

    assert graph.mark_document_reindexed(env.services, env.kb_id, doc_id) is False

    assert store.counts() == (0, 0)
    assert store.document_states()[doc_id].status == STATUS_PENDING


def test_reindexing_asks_for_extraction_when_a_model_is_ready(
    env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc_id = _document(env, "plan.md", ["one"])
    SqliteKnowledgeGraphStore(env.kb_id).mark_document(doc_id, STATUS_READY)
    monkeypatch.setattr(graph, "get_graph_capability", lambda *_args: {"usable": True})

    assert graph.mark_document_reindexed(env.services, env.kb_id, doc_id) is True


def test_enqueue_base_graph_queues_documents_and_forgets_deleted_ones(
    env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph.reset_graph_semaphore_for_tests()
    kept = _document(env, "plan.md", ["one"])
    store = SqliteKnowledgeGraphStore(env.kb_id)
    store.replace_document("gone", [_graph(0, [("Alice", "Apollo", "leads", "", 8)])])
    built: list[str] = []
    monkeypatch.setattr(
        graph, "build_document_graph", lambda _services, _kb, doc_id: built.append(doc_id)
    )

    async def run() -> int:
        count = graph.enqueue_base_graph(env.services, env.kb_id, [kept])
        await asyncio.sleep(0)
        await asyncio.gather(
            *(task for task in asyncio.all_tasks() if task is not asyncio.current_task())
        )
        return count

    assert asyncio.run(run()) == 1
    assert built == [kept]
    assert set(store.document_states()) == {kept}
    assert store.document_states()[kept].status == STATUS_PENDING


def test_a_failed_background_build_does_not_raise(
    env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph.reset_graph_semaphore_for_tests()

    def boom(*_args: object) -> None:
        raise RuntimeError("provider is down")

    monkeypatch.setattr(graph, "build_document_graph", boom)

    async def run() -> None:
        await graph.enqueue_document_graph(env.services, env.kb_id, "doc-1")

    asyncio.run(run())


def test_startup_requeues_documents_left_pending_or_processing(
    env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph.reset_graph_semaphore_for_tests()
    store = SqliteKnowledgeGraphStore(env.kb_id)
    store.replace_document("done", [_graph(0, [("Alice", "Apollo", "leads", "", 8)])])
    store.mark_document("queued", STATUS_PENDING)
    store.mark_document("interrupted", "processing")
    store.mark_document("failed", STATUS_FAILED, error="boom")
    built: list[str] = []
    monkeypatch.setattr(
        graph, "build_document_graph", lambda _services, _kb, doc_id: built.append(doc_id)
    )
    usable = {"usable": False}
    monkeypatch.setattr(graph, "get_graph_capability", lambda *_args: usable)

    async def run() -> None:
        graph.resume_pending_graph_jobs(env.services)
        await asyncio.sleep(0)
        await asyncio.gather(
            *(task for task in asyncio.all_tasks() if task is not asyncio.current_task())
        )

    asyncio.run(run())
    assert built == []

    usable["usable"] = True
    asyncio.run(run())
    assert sorted(built) == ["interrupted", "queued"]


def test_startup_survives_unreadable_graph_storage(
    env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object) -> None:
        raise RuntimeError("graph storage is unavailable")

    monkeypatch.setattr(graph, "get_graph_capability", lambda *_args: {"usable": True})
    monkeypatch.setattr(graph, "open_knowledge_graph", boom)

    graph.resume_pending_graph_jobs(env.services)


def _seed(env: SimpleNamespace) -> SqliteKnowledgeGraphStore:
    store = SqliteKnowledgeGraphStore(env.kb_id)
    store.replace_document(
        "doc-1",
        [
            _graph(0, [("Apollo", "Alice", "is led by", "Alice leads Apollo.", 9)]),
            _graph(1, [("Alice", "Finance Board", "reports budgets to", "", 7)]),
            _graph(2, [("Zeus", "Bob", "is led by", "", 9)]),
        ],
    )
    return store


def test_expand_query_returns_direct_then_indirect_relations(env: SimpleNamespace) -> None:
    expansion = graph.expand_query(_seed(env), "Who approves the budget of Apollo?")

    assert expansion.facts == (
        "Apollo -> is led by -> Alice: Alice leads Apollo.",
        "Alice -> reports budgets to -> Finance Board",
    )
    # The passage a second hop away adds its relation, but is not pulled in itself.
    assert expansion.chunks == (("doc-1", 0),)


def test_expand_query_ignores_names_inside_longer_ascii_words(env: SimpleNamespace) -> None:
    store = SqliteKnowledgeGraphStore(env.kb_id)
    store.replace_document("doc-1", [_graph(0, [("AI", "Zeus", "powers", "", 9)])])

    assert graph.expand_query(store, "How do we maintain it?") == graph.GraphExpansion()
    assert graph.expand_query(store, "What does AI power?").facts == ("AI -> powers -> Zeus",)
    assert graph.expand_query(store, "AI是什么").facts == ("AI -> powers -> Zeus",)


def test_expand_query_without_a_named_entity_adds_nothing(env: SimpleNamespace) -> None:
    assert graph.expand_query(_seed(env), "What is the weather?") == graph.GraphExpansion()
    assert (
        graph.expand_query(SqliteKnowledgeGraphStore("empty"), "Apollo") == graph.GraphExpansion()
    )


def test_expand_query_includes_passages_that_only_mention_the_entity(
    env: SimpleNamespace,
) -> None:
    store = SqliteKnowledgeGraphStore(env.kb_id)
    store.replace_document(
        "doc-1", [ChunkGraph(ordinal=4, entities=(ChunkEntity("Apollo", "product"),))]
    )

    expansion = graph.expand_query(store, "Tell me about Apollo")

    assert expansion.facts == ()
    assert expansion.chunks == (("doc-1", 4),)


def test_graph_view_merges_relations_between_a_pair_into_one_edge(env: SimpleNamespace) -> None:
    store = SqliteKnowledgeGraphStore(env.kb_id)
    store.replace_document(
        "doc-1",
        [
            _graph(
                0,
                [
                    ("Alice", "Apollo", "leads", "", 8),
                    ("Apollo", "Alice", "is owned by", "", 4),
                    ("Bob", "Apollo", "tests", "", 2),
                ],
            )
        ],
    )

    view = graph.graph_view(store, limit=10)

    assert [(node["id"], node["degree"]) for node in view["nodes"]] == [
        ("alice", 1),
        ("apollo", 2),
        ("bob", 1),
    ]
    assert view["edges"] == [
        {"source": "alice", "target": "apollo", "labels": ["leads", "is owned by"], "weight": 12.0},
        {"source": "bob", "target": "apollo", "labels": ["tests"], "weight": 2.0},
    ]
    assert [node["id"] for node in graph.graph_view(store, limit=10, search="bo")["nodes"]] == [
        "bob"
    ]
    assert graph.graph_view(store, limit=1)["edges"] == []


def test_graph_stats_count_document_states(env: SimpleNamespace) -> None:
    store = SqliteKnowledgeGraphStore(env.kb_id)
    assert graph.graph_stats(store, ["a", "b"])["built"] is False
    store.replace_document("a", [_graph(0, [("Alice", "Apollo", "leads", "", 8)])])
    store.replace_document("b", [], error="1 of 2 passages could not be extracted")
    store.mark_document("c", STATUS_PENDING)
    store.mark_document("d", STATUS_FAILED, error="boom")
    store.mark_document("deleted", STATUS_READY)

    assert graph.graph_stats(store, ["a", "b", "c", "d", "new"]) == {
        "built": True,
        "entities": 2,
        "relations": 1,
        "documents_total": 5,
        "documents_ready": 2,
        "documents_partial": 1,
        "documents_pending": 1,
        "documents_failed": 1,
    }


def test_entity_view_lists_relations_and_source_passages(env: SimpleNamespace) -> None:
    doc_id = _document(env, "plan.md", ["Alice leads Apollo.", "Unrelated."])
    hidden = _document(env, "draft.md", ["Alice drafts."], status="pending")
    store = SqliteKnowledgeGraphStore(env.kb_id)
    store.replace_document(doc_id, [_graph(0, [("Alice", "Apollo", "leads", "Why.", 8)])])
    store.replace_document(hidden, [_graph(0, [("Alice", "Draft", "writes", "", 3)])])

    view = graph.entity_view(env.services, env.kb_id, " ALICE ")

    assert view["entity"] == {
        "id": "alice",
        "name": "Alice",
        "type": "concept",
        "description": "About Alice.",
        "mentions": 2,
    }
    assert view["relations"][0] == {
        "source": {"id": "alice", "name": "Alice"},
        "target": {"id": "apollo", "name": "Apollo"},
        "label": "leads",
        "description": "Why.",
        "weight": 8.0,
    }
    # Passages of documents that are not searchable are left out.
    assert view["passages"] == [
        {
            "doc_id": doc_id,
            "filename": "plan.md",
            "path": "plan.md",
            "ordinal": 0,
            "text": "Alice leads Apollo.",
        }
    ]
    with pytest.raises(LookupError, match="knowledge graph entity not found"):
        graph.entity_view(env.services, env.kb_id, "nobody")
