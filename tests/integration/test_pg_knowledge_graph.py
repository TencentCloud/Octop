"""Knowledge-graph rows on a live PostgreSQL.

Uses ``OCTOP_TEST_DATABASE_URL``. Drops only the ``public.knowledge_graph_*``
tables. Does not reset the rest of ``public``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from octop.config import DatabaseConfig
from octop.infra.knowledge.graph import expand_query, graph_view, open_knowledge_graph
from octop.infra.knowledge.graph_store import (
    STATUS_PENDING,
    STATUS_READY,
    ChunkEntity,
    ChunkGraph,
    ChunkRelation,
    PgKnowledgeGraphStore,
)
from tests.support.postgresql import requires_postgresql

pytestmark = requires_postgresql

_TABLES = (
    "public.knowledge_graph_entities",
    "public.knowledge_graph_relations",
    "public.knowledge_graph_documents",
)


def _drop_tables(database: DatabaseConfig) -> None:
    import psycopg

    with psycopg.connect(database.postgresql_conninfo()) as conn:
        for table in _TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()


@pytest.fixture
def database() -> Iterator[DatabaseConfig]:
    from octop.config import _parse_database_url

    parsed = _parse_database_url(os.environ["OCTOP_TEST_DATABASE_URL"])
    config = DatabaseConfig(
        driver="postgresql",
        host=str(parsed["host"]),
        port=int(parsed["port"]),
        database=str(parsed["database"]),
        user=str(parsed.get("user") or "postgres"),
        password=parsed.get("password"),
        url=str(parsed["url"]),
    )
    _drop_tables(config)
    yield config
    _drop_tables(config)


def _chunk(ordinal: int, relations: list[tuple[str, str, str, str, float]]) -> ChunkGraph:
    names = dict.fromkeys(end for source, target, *_ in relations for end in (source, target))
    return ChunkGraph(
        ordinal=ordinal,
        entities=tuple(ChunkEntity(name, "concept", f"About {name}.") for name in names),
        relations=tuple(ChunkRelation(*relation) for relation in relations),
    )


def test_graph_round_trip_and_isolation_between_knowledge_bases(
    database: DatabaseConfig,
) -> None:
    services = SimpleNamespace(config=SimpleNamespace(database=database))
    store = open_knowledge_graph(services, "kb-1")
    assert isinstance(store, PgKnowledgeGraphStore)
    other = PgKnowledgeGraphStore("kb-2", database)

    assert store.exists() is False
    store.replace_document(
        "doc-1",
        [
            _chunk(0, [("Apollo", "Alice", "is led by", "Alice leads Apollo.", 9)]),
            _chunk(1, [("apollo", "alice", "is led by", "", 6)]),
            _chunk(2, [("Alice", "Finance Board", "reports budgets to", "", 7)]),
        ],
    )
    store.replace_document("doc-2", [_chunk(0, [("100% Cotton", "a_c", "contains", "", 5)])])
    other.replace_document("doc-9", [_chunk(0, [("Zeus", "Bob", "is led by", "", 9)])])

    assert store.exists() is True
    assert store.counts() == (5, 3)
    assert other.counts() == (2, 1)
    assert store.entities(["apollo"])["apollo"].mentions == 2
    led = next(item for item in store.relations_of(["apollo"]) if item.label == "is led by")
    assert led.weight == 15
    assert led.chunks == (("doc-1", 0), ("doc-1", 1))
    assert store.top_entity_keys(1) == ["alice"]
    # % and _ in names and search fragments are literal characters on PostgreSQL too.
    assert store.top_entity_keys(10, search="%") == ["100% cotton"]
    assert store.match_keys("is 100% cotton soft?") == ["100% cotton"]
    assert store.match_keys("abc") == []

    expansion = expand_query(store, "Who approves the budget of Apollo?")
    assert expansion.facts == (
        "Apollo -> is led by -> Alice: Alice leads Apollo.",
        "Alice -> reports budgets to -> Finance Board",
    )
    assert expansion.chunks == (("doc-1", 0), ("doc-1", 1))
    assert len(graph_view(store, limit=10)["edges"]) == 3

    store.mark_document("doc-1", STATUS_PENDING)
    assert store.counts() == (2, 1)
    assert store.document_states()["doc-1"].status == STATUS_PENDING
    assert store.document_states()["doc-2"].status == STATUS_READY
    store.delete_document("doc-2")
    assert store.counts() == (0, 0)
    store.clear()
    assert store.exists() is False
    assert other.counts() == (2, 1)
