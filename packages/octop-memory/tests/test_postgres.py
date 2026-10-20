"""Tests for PostgresMemoryBackend.

These tests require a running PostgreSQL instance. They are automatically skipped
when psycopg is not installed or when the database is unreachable.

Set TEST_POSTGRES_DSN to override the default connection string:
    export TEST_POSTGRES_DSN="postgresql://user:pass@localhost/octop_memory_test"
"""

from __future__ import annotations

import contextlib
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

try:
    import psycopg
    from psycopg.pq import TransactionStatus

    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False

pytestmark = [
    pytest.mark.skipif(not PG_AVAILABLE, reason="psycopg not installed"),
    pytest.mark.usefixtures("postgres_dsn"),
]

DSN = os.environ.get("TEST_POSTGRES_DSN", "postgresql://localhost/octop_memory_test")


def _open_backend(ns: str):
    from octop_memory.storage.backends.postgres import PostgresMemoryBackend

    return PostgresMemoryBackend(namespace=ns, dsn=DSN)


@pytest.fixture
def backend():
    """Create a PostgresMemoryBackend with a unique namespace, purge it after the test."""
    # Generate a unique namespace per test run to avoid collisions
    ns = f"test_{uuid.uuid4().hex[:12]}"
    be = _open_backend(ns)

    yield be

    # Cleanup: delete this namespace's rows from the shared tables
    try:
        if be._closed:
            # TestClose closes it on purpose; reopen so this namespace's rows
            # still get cleaned out of the shared tables.
            be = _open_backend(ns)
        be.purge_namespace()
    finally:
        be.close()


# Import types here so they're available for all tests
from octop_memory.types import (  # noqa: E402
    AtomCard,
    MemoryNode,
)


class TestSaveAndGetNode:
    def test_save_and_get_children(self, backend) -> None:
        root = MemoryNode(
            id="a0000000-0000-0000-0000-000000000001",
            parent_id=None,
            level="root",
            content="Global",
            topic=None,
            conversation_id=None,
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            updated_at=datetime(2026, 5, 24, tzinfo=UTC),
        )
        branch = MemoryNode(
            id="a0000000-0000-0000-0000-000000000002",
            parent_id="a0000000-0000-0000-0000-000000000001",
            level="branch",
            content="Project work",
            topic="dev",
            conversation_id=None,
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            updated_at=datetime(2026, 5, 24, tzinfo=UTC),
        )
        backend.save_node(root)
        backend.save_node(branch)

        children = backend.get_children(None)
        assert len(children) == 1
        assert children[0].id == "a0000000-0000-0000-0000-000000000001"

        branch_children = backend.get_children("a0000000-0000-0000-0000-000000000001")
        assert len(branch_children) == 1
        assert branch_children[0].id == "a0000000-0000-0000-0000-000000000002"

    def test_duplicate_id_raises(self, backend) -> None:
        """save_node is a strict insert — same id twice must raise, not overwrite."""
        node = MemoryNode(
            id="a0000000-0000-0000-0000-000000000010",
            parent_id=None,
            level="root",
            content="Original",
            topic=None,
            conversation_id=None,
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            updated_at=datetime(2026, 5, 24, tzinfo=UTC),
        )
        backend.save_node(node)

        dup = MemoryNode(
            id="a0000000-0000-0000-0000-000000000010",
            parent_id=None,
            level="root",
            content="Should not overwrite",
            topic="new-topic",
            conversation_id=None,
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            updated_at=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            backend.save_node(dup)

        tree = backend.get_tree()
        assert len(tree) == 1
        assert tree[0].content == "Original"

    def test_update_node(self, backend) -> None:
        node = MemoryNode(
            id="a0000000-0000-0000-0000-000000000003",
            parent_id=None,
            level="root",
            content="Old content",
            topic=None,
            conversation_id=None,
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            updated_at=datetime(2026, 5, 24, tzinfo=UTC),
        )
        backend.save_node(node)
        backend.update_node("a0000000-0000-0000-0000-000000000003", content="New content", topic="updated")

        tree = backend.get_tree()
        assert tree[0].content == "New content"
        assert tree[0].topic == "updated"


class TestSearchMemories:
    def test_fts_finds_matching_nodes(self, backend) -> None:
        texts = ["Python backend development", "React frontend UI", "Database design patterns"]
        for i, text in enumerate(texts):
            _save_atom_leaf(backend, i=i, assertion=text)

        results = backend.search_memories("Python", limit=5)
        assert len(results) >= 1
        assert "Python" in results[0].content

    def test_fts_matches_topic(self, backend) -> None:
        _save_atom_leaf(
            backend,
            i=10,
            assertion="Some generic content",
            search_terms=["kubernetes deployment"],
            topic="kubernetes deployment",
        )

        results = backend.search_memories("kubernetes", limit=5)
        assert len(results) >= 1


def _save_atom_leaf(
    backend,
    *,
    i: int,
    assertion: str,
    search_terms: list[str] | None = None,
    topic: str | None = None,
) -> None:
    now = datetime(2026, 5, 24, tzinfo=UTC)
    suffix = f"{i:012d}"
    atom_id = f"b0000000-0000-0000-0000-{suffix}"
    backend.save_atom(
        AtomCard(
            id=atom_id,
            entity_id=f"e0000000-0000-0000-0000-{suffix}",
            candidate_id=f"c0000000-0000-0000-0000-{suffix}",
            raw_event_ids=[],
            assertion=assertion,
            verbatim_quote=assertion,
            quote_event_id=f"a0000000-0000-0000-0000-{suffix}",
            search_terms=search_terms or [],
            occurred_at=now,
            confidence="high",
            importance="medium",
            created_at=now,
        )
    )
    backend.save_node(
        MemoryNode(
            id=f"d0000000-0000-0000-0000-{suffix}",
            parent_id=None,
            level="leaf",
            content=assertion,
            topic=topic,
            conversation_id=None,
            created_at=now,
            updated_at=now,
            atom_id=atom_id,
        )
    )


class TestGetTree:
    def test_returns_all_nodes(self, backend) -> None:
        now = datetime(2026, 5, 24, tzinfo=UTC)
        backend.save_node(
            MemoryNode(
                id="d0000000-0000-0000-0000-000000000001",
                parent_id=None,
                level="root",
                content="root",
                topic=None,
                conversation_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        backend.save_node(
            MemoryNode(
                id="d0000000-0000-0000-0000-000000000002",
                parent_id="d0000000-0000-0000-0000-000000000001",
                level="branch",
                content="branch",
                topic="t",
                conversation_id=None,
                created_at=now,
                updated_at=now,
            )
        )

        tree = backend.get_tree()
        assert len(tree) == 2
        ids = {n.id for n in tree}
        assert ids == {"d0000000-0000-0000-0000-000000000001", "d0000000-0000-0000-0000-000000000002"}


class TestClose:
    def test_close_closes_connection(self, backend) -> None:
        backend.close()
        assert backend._closed


class TestTransactionLifecycle:
    def test_init_leaves_connection_idle(self, backend: Any) -> None:
        assert backend._conn is None

    def test_read_operation_finishes_its_transaction(self, backend: Any) -> None:
        assert backend.list_episodes() == []
        assert backend._conn is None

    def test_explicit_transaction_still_spans_multiple_operations(self, backend: Any) -> None:
        with backend.transaction():
            assert backend.list_episodes() == []
            assert backend.count_stats()["raw_events"] == 0
            assert backend._conn.info.transaction_status == TransactionStatus.INTRANS
        assert backend._conn is None

    def test_scoped_fts_indexes_are_noop_after_first_boot(self, backend: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        def unexpected_extension_install() -> bool:
            raise AssertionError("already-migrated indexes must not run DDL")

        monkeypatch.setattr(backend, "_enable_btree_gin", unexpected_extension_install)
        with backend._cursor() as cur:
            backend._scope_fts_indexes_by_namespace(cur)


class TestNamespaceIsolation:
    """Two agents sharing the same fixed tables must never see each other's rows."""

    def test_shared_tables_isolate_namespaces(self, backend) -> None:
        other = _open_backend(f"test_{uuid.uuid4().hex[:12]}")
        try:
            _save_atom_leaf(backend, i=1, assertion="agent one Python fact")
            _save_atom_leaf(other, i=1, assertion="agent two Python fact")

            assert len(backend.get_tree()) == 1
            assert len(other.get_tree()) == 1
            assert backend.get_tree()[0].content == "agent one Python fact"
            assert other.get_tree()[0].content == "agent two Python fact"

            # FTS search stays inside the namespace
            hits = backend.search_memories("Python", limit=10)
            assert [h.content for h in hits] == ["agent one Python fact"]

            # Same id in another namespace is not a conflict (composite PK)
            suffix = f"{1:012d}"
            assert backend.get_atom(f"b0000000-0000-0000-0000-{suffix}") is not None

            # Stats are per-namespace
            assert backend.count_stats()["atoms"] == 1

            # Purging one namespace leaves the other intact
            deleted = other.purge_namespace()
            assert deleted > 0
            assert other.get_tree() == []
            assert len(backend.get_tree()) == 1
        finally:
            other.purge_namespace()
            other.close()


class TestLegacySchemaMigration:
    """Old one-schema-per-namespace layouts are auto-copied into shared tables."""

    def test_legacy_rows_migrated_and_schema_renamed(self) -> None:
        from octop_memory.storage.backends.postgres import PostgresMemoryBackend

        ns = f"test_{uuid.uuid4().hex[:12]}"
        try:
            seed = psycopg.connect(DSN)
        except psycopg.OperationalError:
            pytest.skip("PostgreSQL not available")
        with seed, seed.cursor() as cur:
            cur.execute(f"CREATE SCHEMA {ns}")
            # Minimal old-layout tables (no tsv, no metadata — column
            # intersection in the migrator must tolerate the drift).
            cur.execute(f"""
                    CREATE TABLE {ns}.raw_events (
                        id TEXT PRIMARY KEY,
                        host TEXT NOT NULL,
                        session_id TEXT,
                        thread_id TEXT,
                        "user" TEXT,
                        timestamp TIMESTAMPTZ NOT NULL,
                        event_type TEXT NOT NULL,
                        content TEXT NOT NULL,
                        payload JSONB NOT NULL DEFAULT '{{}}'::jsonb
                    )
                """)
            cur.execute(
                f"""INSERT INTO {ns}.raw_events
                        (id, host, timestamp, event_type, content)
                        VALUES ('evt_legacy1', 'cli', now(), 'message', 'legacy hello')"""
            )
        seed.close()

        be = PostgresMemoryBackend(namespace=ns, dsn=DSN)
        try:
            got = be.get_raw("evt_legacy1")
            assert got is not None
            assert got.content == "legacy hello"

            # Legacy schema is renamed out of the way, not dropped
            with be._cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                    (ns,),
                )
                assert cur.fetchone() is None
                backup = f"{ns[:56]}__old"
                cur.execute(
                    "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                    (backup,),
                )
                assert cur.fetchone() is not None
                cur.execute(f"DROP SCHEMA {backup} CASCADE")
        finally:
            be.purge_namespace()
            be.close()


class TestAbortedConnectionRecovery:
    """psycopg refuses *every* command on a connection left in ``INERROR``.

    One failed statement from anywhere used to disable memory reads and writes
    for the rest of the process; only ``transaction()`` and one write method
    recovered. Every data-access method now goes through ``_cursor()``.
    """

    @staticmethod
    def _poison(backend: Any) -> None:
        with backend._connection() as conn:
            with contextlib.suppress(psycopg.Error), conn.cursor() as cur:
                cur.execute("SELECT * FROM a_table_that_does_not_exist")
            assert conn.info.transaction_status == TransactionStatus.INERROR

    def test_reads_recover(self, backend: Any) -> None:
        self._poison(backend)
        assert backend.get_raw("anything") is None
        assert backend.count_stats()["raw_events"] == 0

    def test_writes_recover(self, backend: Any) -> None:
        from datetime import UTC, datetime

        from octop_memory.types import RawEvent

        self._poison(backend)
        backend.save_raw(
            RawEvent(
                id="after-poison",
                host="manual",
                session_id=None,
                thread_id=None,
                user=None,
                timestamp=datetime.now(UTC),
                event_type="manual",
                content="written after a failed statement",
            )
        )
        assert backend.get_raw("after-poison") is not None

    def test_an_explicit_transaction_still_owns_its_rollback(self, backend: Any) -> None:
        """The recovery must not paper over a failure inside a caller's
        transaction block — that block has to see the error and roll back.
        """
        from datetime import UTC, datetime

        from octop_memory.types import RawEvent

        with pytest.raises(psycopg.Error), backend.transaction():
            backend.save_raw(
                RawEvent(
                    id="doomed",
                    host="manual",
                    session_id=None,
                    thread_id=None,
                    user=None,
                    timestamp=datetime.now(UTC),
                    event_type="manual",
                    content="rolled back",
                )
            )
            with backend._cursor() as cur:
                cur.execute("SELECT * FROM a_table_that_does_not_exist")

        assert backend.get_raw("doomed") is None


class TestExportDoesNotPoisonTheConnection:
    """Regression: the exporter duck-typed on ``_conn`` / ``_ns``, which this
    backend also exposes, so a SQLite statement reached psycopg. The
    ``UndefinedTable`` was swallowed without a rollback, leaving the
    connection aborted — every later write in the process then failed with
    ``InFailedSqlTransaction``, and the dump silently lost this table.
    """

    def test_writes_still_work_after_an_export(self, backend: Any, tmp_path: Any) -> None:
        from datetime import UTC, datetime

        from octop_memory.core import Memory
        from octop_memory.operations.migration.export import export_namespace
        from octop_memory.types import ActiveEntity, RawEvent

        memory = Memory(namespace=backend._ns, backend=backend)
        now = datetime.now(UTC)
        backend.upsert_active_entity(
            ActiveEntity(thread_id="t1", entity_id="e1", last_seen_at=now, source="query_mention")
        )

        export_namespace(memory, tmp_path / "dump.jsonl")

        assert backend._conn is None
        backend.save_raw(
            RawEvent(
                id="after-export",
                host="manual",
                session_id=None,
                thread_id=None,
                user=None,
                timestamp=now,
                event_type="manual",
                content="written after the export",
            )
        )
        assert backend.get_raw("after-export") is not None

    def test_active_entities_reach_the_dump(self, backend: Any, tmp_path: Any) -> None:
        import json
        from datetime import UTC, datetime

        from octop_memory.core import Memory
        from octop_memory.operations.migration.export import export_namespace
        from octop_memory.types import ActiveEntity

        backend.upsert_active_entity(
            ActiveEntity(thread_id="t1", entity_id="e1", last_seen_at=datetime.now(UTC), source="query_mention")
        )
        out = tmp_path / "dump.jsonl"
        export_namespace(Memory(namespace=backend._ns, backend=backend), out)

        rows = [
            json.loads(line)["data"]
            for line in out.read_text(encoding="utf-8").splitlines()
            if json.loads(line)["table"] == "thread_active_entities"
        ]
        assert [(r["thread_id"], r["entity_id"], r["source"]) for r in rows] == [("t1", "e1", "query_mention")]


def _root_node(label: str) -> MemoryNode:
    ts = datetime(2026, 8, 31, tzinfo=UTC)
    return MemoryNode(
        id=str(uuid.uuid4()),
        parent_id=None,
        level="root",
        content=label,
        topic=None,
        conversation_id=None,
        created_at=ts,
        updated_at=ts,
    )


class TestDeadConnectionRecovery:
    """A connection dropped by the server, as opposed to one left aborted.

    ``rollback()`` cannot recover this one — ``TestAbortedConnectionRecovery``
    covers that failure. Here the socket is gone and only a redial helps.
    """

    @staticmethod
    def _kill(backend: Any) -> None:
        """Drop a borrowed session; the pool must discard it on return."""
        with backend._connection() as conn:
            with psycopg.connect(DSN, autocommit=True) as admin:
                admin.execute("SELECT pg_terminate_backend(%s)", (conn.info.backend_pid,))
            with contextlib.suppress(psycopg.Error):
                conn.execute("SELECT 1")
            assert conn.closed

    def test_reads_recover(self, backend: Any) -> None:
        self._kill(backend)
        assert backend.get_node("missing") is None

    def test_writes_recover(self, backend: Any) -> None:
        self._kill(backend)
        node = _root_node("after-redial")
        backend.save_node(node)
        assert backend.get_node(node.id) is not None

    def test_search_path_is_restored(self, backend: Any) -> None:
        """Unqualified table names must still resolve on the new connection."""
        from octop_memory.storage.backends.postgres import SHARED_SCHEMA

        self._kill(backend)
        with backend._cursor() as cur:
            cur.execute("SHOW search_path")
            row = cur.fetchone()
        assert SHARED_SCHEMA in str(row["search_path"])

    def test_close_is_not_undone(self, backend: Any) -> None:
        """A deliberate close must stay closed, not silently reopen."""
        backend.close()
        with pytest.raises(psycopg.OperationalError):
            backend.get_node("anything")
        assert backend._closed

    def test_an_open_transaction_refuses_to_redial(self, backend: Any) -> None:
        """Reconnecting mid-block would commit a half-applied change set."""
        with pytest.raises(psycopg.Error), backend.transaction():
            backend.save_node(_root_node("first-half"))
            self._kill(backend)
            backend.save_node(_root_node("second-half"))
