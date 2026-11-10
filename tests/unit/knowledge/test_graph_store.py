"""Unit tests for the per-knowledge-base entity graph storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.knowledge.graph_store import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_READY,
    ChunkEntity,
    ChunkGraph,
    ChunkRelation,
    SqliteKnowledgeGraphStore,
    entity_key,
)


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SqliteKnowledgeGraphStore:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    return SqliteKnowledgeGraphStore("kb-1")


def _chunk(
    ordinal: int, entities: list[tuple[str, str, str]], relations: list[tuple]
) -> ChunkGraph:
    return ChunkGraph(
        ordinal=ordinal,
        entities=tuple(
            ChunkEntity(name, kind, description) for name, kind, description in entities
        ),
        relations=tuple(ChunkRelation(*relation) for relation in relations),
    )


def test_entity_key_ignores_case_and_spacing() -> None:
    assert entity_key("  Tencent   Cloud ") == entity_key("tencent cloud") == "tencent cloud"


def test_reads_on_a_knowledge_base_without_a_graph_create_nothing(
    store: SqliteKnowledgeGraphStore,
) -> None:
    assert store.exists() is False
    assert store.counts() == (0, 0)
    assert store.match_keys("anything") == []
    store.delete_document("doc-1")
    store.clear()
    assert not store.path.exists()


def test_entities_are_merged_by_name_across_chunks_and_documents(
    store: SqliteKnowledgeGraphStore,
) -> None:
    store.replace_document(
        "doc-1",
        [
            _chunk(0, [("Tencent Cloud", "organization", "A cloud provider.")], []),
            _chunk(1, [("tencent  cloud", "organization", "")], []),
        ],
    )
    store.replace_document(
        "doc-2",
        [_chunk(0, [("Tencent Cloud", "product", "A cloud provider based in Shenzhen.")], [])],
    )

    merged = store.entities(["tencent cloud"])["tencent cloud"]

    assert merged.name == "Tencent Cloud"
    assert merged.type == "organization"
    assert merged.description == "A cloud provider based in Shenzhen."
    assert merged.mentions == 3
    assert store.counts() == (1, 0)
    assert store.entity_chunks("tencent cloud") == [("doc-1", 0), ("doc-1", 1), ("doc-2", 0)]


def test_relations_are_merged_with_summed_weight_and_source_chunks(
    store: SqliteKnowledgeGraphStore,
) -> None:
    entities = [("Alice", "person", ""), ("Apollo", "product", ""), ("Bob", "person", "")]
    store.replace_document(
        "doc-1",
        [
            _chunk(0, entities, [("Alice", "Apollo", "leads", "Alice leads Apollo.", 8)]),
            _chunk(
                1,
                entities,
                [("alice", "apollo", "leads", "", 6), ("Bob", "Apollo", "tests", "", 3)],
            ),
        ],
    )

    relations = store.relations_of(["alice"])

    assert len(relations) == 1
    assert (relations[0].source, relations[0].target, relations[0].label) == (
        "alice",
        "apollo",
        "leads",
    )
    assert relations[0].weight == 14
    assert relations[0].description == "Alice leads Apollo."
    assert relations[0].chunks == (("doc-1", 0), ("doc-1", 1))
    assert [item.label for item in store.relations_of(["apollo"])] == ["leads", "tests"]
    assert [item.label for item in store.relations_among(["alice", "apollo"])] == ["leads"]
    assert store.counts() == (3, 2)


def test_self_relations_and_blank_names_are_not_stored(store: SqliteKnowledgeGraphStore) -> None:
    store.replace_document(
        "doc-1",
        [
            _chunk(
                0,
                [("Alice", "person", ""), ("   ", "person", "")],
                [("Alice", "alice", "is", "", 5), ("Alice", "", "knows", "", 5)],
            )
        ],
    )

    assert store.counts() == (1, 0)


def test_top_entity_keys_rank_by_mentions_and_filter_by_fragment(
    store: SqliteKnowledgeGraphStore,
) -> None:
    store.replace_document(
        "doc-1",
        [
            _chunk(0, [("Apollo", "product", ""), ("Zeus", "product", "")], []),
            _chunk(1, [("Apollo", "product", ""), ("100% Cotton", "concept", "")], []),
        ],
    )

    assert store.top_entity_keys(2) == ["apollo", "100% cotton"]
    assert store.top_entity_keys(10, search="ZEU") == ["zeus"]
    # % is a literal character in a search fragment, not a wildcard.
    assert store.top_entity_keys(10, search="%") == ["100% cotton"]
    assert store.top_entity_keys(0) == []


def test_match_keys_finds_names_inside_a_query(store: SqliteKnowledgeGraphStore) -> None:
    store.replace_document(
        "doc-1",
        [
            _chunk(
                0,
                [("阿波罗项目", "product", ""), ("Apollo", "product", ""), ("a_c", "other", "")],
                [],
            )
        ],
    )

    assert store.match_keys("谁负责阿波罗项目的预算？") == ["阿波罗项目"]
    assert store.match_keys("Who leads APOLLO?") == ["apollo"]
    # _ is a literal character in a name, not a single-character wildcard.
    assert store.match_keys("abc") == []
    assert store.match_keys("") == []


def test_replacing_a_document_drops_what_it_contributed_before(
    store: SqliteKnowledgeGraphStore,
) -> None:
    store.replace_document("doc-1", [_chunk(0, [("Old", "concept", "")], [])])
    store.replace_document("doc-1", [_chunk(0, [("New", "concept", "")], [])], error="note")

    assert store.top_entity_keys(10) == ["new"]
    state = store.document_states()["doc-1"]
    assert (state.status, state.error) == (STATUS_READY, "note")


def test_marking_a_document_not_ready_drops_its_rows_but_keeps_the_graph(
    store: SqliteKnowledgeGraphStore,
) -> None:
    store.replace_document("doc-1", [_chunk(0, [("Apollo", "product", "")], [])])

    store.mark_document("doc-1", STATUS_PENDING)

    assert store.counts() == (0, 0)
    assert store.exists() is True
    store.mark_document("doc-1", STATUS_FAILED, error="boom")
    assert store.document_states()["doc-1"].error == "boom"


def test_delete_document_and_clear(store: SqliteKnowledgeGraphStore) -> None:
    store.replace_document("doc-1", [_chunk(0, [("Apollo", "product", "")], [])])
    store.replace_document("doc-2", [_chunk(0, [("Zeus", "product", "")], [])])

    store.delete_document("doc-1")

    assert store.top_entity_keys(10) == ["zeus"]
    assert set(store.document_states()) == {"doc-2"}
    store.clear()
    assert store.exists() is False
    assert store.counts() == (0, 0)


def test_graphs_of_two_knowledge_bases_are_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    first, second = SqliteKnowledgeGraphStore("kb-1"), SqliteKnowledgeGraphStore("kb-2")
    first.replace_document("doc-1", [_chunk(0, [("Apollo", "product", "")], [])])

    assert second.exists() is False
    assert first.path != second.path
