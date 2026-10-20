"""Tests for SqliteMemoryBackend."""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import (
    JournalEntry,
    MemoryNode,
    RawEvent,
)


@pytest.fixture
def backend(tmp_path: Path) -> SqliteMemoryBackend:
    db_path = tmp_path / "test.sqlite"
    return SqliteMemoryBackend(namespace="test", db_path=str(db_path))


class TestSaveAndGetNode:
    def test_namespace_is_sanitized_for_table_prefix(self, tmp_path: Path) -> None:
        backend = SqliteMemoryBackend(namespace="OpenClaw Prod/1", db_path=tmp_path / "ns.sqlite")
        assert backend._ns == "openclaw_prod_1"

        node = MemoryNode(
            id="n1",
            parent_id=None,
            level="root",
            content="Namespace sanitizer smoke test",
            topic=None,
            conversation_id=None,
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            updated_at=datetime(2026, 5, 24, tzinfo=UTC),
        )
        backend.save_node(node)
        assert backend.get_node("n1") is not None

    def test_save_and_get_children(self, backend: SqliteMemoryBackend) -> None:
        root = MemoryNode(
            id="root1",
            parent_id=None,
            level="root",
            content="Global",
            topic=None,
            conversation_id=None,
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            updated_at=datetime(2026, 5, 24, tzinfo=UTC),
        )
        branch = MemoryNode(
            id="b1",
            parent_id="root1",
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
        assert children[0].id == "root1"

        branch_children = backend.get_children("root1")
        assert len(branch_children) == 1
        assert branch_children[0].id == "b1"

    def test_update_node(self, backend: SqliteMemoryBackend) -> None:
        node = MemoryNode(
            id="n1",
            parent_id=None,
            level="root",
            content="Old content",
            topic=None,
            conversation_id=None,
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            updated_at=datetime(2026, 5, 24, tzinfo=UTC),
        )
        backend.save_node(node)
        backend.update_node("n1", content="New content", topic="updated")

        tree = backend.get_tree()
        assert tree[0].content == "New content"
        assert tree[0].topic == "updated"


class TestSearchMemories:
    def test_fts_finds_matching_nodes(self, backend: SqliteMemoryBackend) -> None:
        memory = Memory(namespace="test", backend=backend)
        memory.store("Python backend development")
        memory.store("React frontend UI")
        memory.store("Database design patterns")

        results = backend.search_memories("Python", limit=5)
        assert len(results) >= 1
        assert "Python" in results[0].content
        assert results[0].atom_id is not None


class TestGetTree:
    def test_returns_all_nodes(self, backend: SqliteMemoryBackend) -> None:
        now = datetime(2026, 5, 24, tzinfo=UTC)
        backend.save_node(
            MemoryNode(
                id="r",
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
                id="b",
                parent_id="r",
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
        assert ids == {"r", "b"}


class TestJournalTargetIndexesArePartial:
    """RISK-026 / ADR-024: journal target_* indexes should skip NULL rows.

    ``extract_run`` rows never set target_entity_id/target_atom_id/
    target_candidate_id, so a plain index on those columns wastes space
    on leaf entries no equality filter can ever match. Verifies both the
    migrated shape and that query results are unaffected.
    """

    def _index_sql(self, backend: SqliteMemoryBackend, suffix: str) -> str | None:
        row = backend._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
            (f"{backend._ns}_journal_{suffix}",),
        ).fetchone()
        return row[0] if row else None

    def test_fresh_database_gets_partial_indexes(self, backend: SqliteMemoryBackend) -> None:
        for suffix in ("target_entity", "target_atom", "target_candidate"):
            sql = self._index_sql(backend, suffix)
            assert sql is not None
            assert "WHERE" in sql.upper()

        # time / action stay plain — every row populates those columns,
        # so a partial predicate would buy nothing.
        for suffix in ("time", "action"):
            sql = self._index_sql(backend, suffix)
            assert sql is not None
            assert "WHERE" not in sql.upper()

    def test_legacy_plain_index_is_migrated_on_reopen(self, tmp_path: Path) -> None:
        db_path = tmp_path / "legacy.sqlite"
        first = SqliteMemoryBackend(namespace="legacy", db_path=str(db_path))
        # Simulate a pre-migration database: drop back to a plain index.
        first._conn.execute("DROP INDEX legacy_journal_target_atom")
        first._conn.execute("CREATE INDEX legacy_journal_target_atom ON legacy_journal(target_atom_id)")
        first._conn.commit()
        first.close()

        reopened = SqliteMemoryBackend(namespace="legacy", db_path=str(db_path))
        sql = self._index_sql(reopened, "target_atom")
        assert sql is not None
        assert "WHERE" in sql.upper()

    def test_partial_index_does_not_change_query_results(self, backend: SqliteMemoryBackend) -> None:
        now = datetime(2026, 8, 11, tzinfo=UTC)
        backend.append_journal(JournalEntry(id="j1", timestamp=now, action="extract_run", actor="auto", note="quiet"))
        backend.append_journal(
            JournalEntry(
                id="j2",
                timestamp=now,
                action="promote",
                actor="auto",
                target_atom_id="atom-1",
                note="promoted",
            )
        )

        hits = backend.list_journal(target_atom_id="atom-1", limit=10)
        assert [e.id for e in hits] == ["j2"]
        # No filter → both rows, including the one with target_atom_id
        # left NULL (i.e. the partial index isn't hiding it from an
        # unfiltered scan — it just never had to index it).
        assert {e.id for e in backend.list_journal(limit=10)} == {"j1", "j2"}


class TestThreadLocalConnections:
    def test_read_and_write_on_separate_threads(self, backend: SqliteMemoryBackend) -> None:
        memory = Memory(namespace="test", backend=backend)
        memory.store("Python backend development")

        errors: list[BaseException] = []
        now = datetime(2026, 8, 14, tzinfo=UTC)

        def writer() -> None:
            try:
                for i in range(40):
                    backend.save_raw(
                        RawEvent(
                            id=f"raw-w-{i}",
                            host="test",
                            session_id="s",
                            thread_id="t",
                            user="u",
                            timestamp=now,
                            event_type="user_message",
                            content=f"hello write {i}",
                            payload={},
                        )
                    )
            except (sqlite3.Error, OSError, RuntimeError, ValueError) as exc:  # collect for the parent thread
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(40):
                    backend.search_atoms("Python", limit=5)
                    backend.search_raw("hello", limit=5)
            except (sqlite3.Error, OSError, RuntimeError, ValueError) as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert backend.get_raw("raw-w-0") is not None

    def test_close_rejects_other_threads_without_reopen(self, backend: SqliteMemoryBackend) -> None:
        backend.close()
        raised: list[BaseException] = []

        def worker() -> None:
            try:
                backend.list_raw(limit=1)
            except sqlite3.ProgrammingError as exc:
                raised.append(exc)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        assert raised
        assert "closed" in str(raised[0]).lower()

    def test_close_rejects_same_thread(self, backend: SqliteMemoryBackend) -> None:
        backend.close()
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            backend.list_raw(limit=1)


class TestAutoVacuumIncrementalOnCreate:
    """New files start INCREMENTAL so nudge_vacuum works without compact (ADR-027)."""

    def test_new_file_is_incremental(self, tmp_path: Path) -> None:
        backend = SqliteMemoryBackend(namespace="fresh", db_path=tmp_path / "fresh.sqlite")
        mode = backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0]
        assert mode == 2  # INCREMENTAL

    def test_legacy_none_file_stays_none_until_vacuum(self, tmp_path: Path) -> None:
        path = tmp_path / "legacy.sqlite"
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("PRAGMA auto_vacuum=NONE")
            conn.execute("CREATE TABLE _pre_existing (x INTEGER)")
            conn.commit()
        finally:
            conn.close()

        backend = SqliteMemoryBackend(namespace="legacy", db_path=path)
        mode = backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0]
        assert mode == 0  # NONE — pragma on open does not rebuild the file


class TestSharedConnectionLifecycle:
    """Live pool workers must not retain a SQLite connection each (Octop#2060)."""

    def test_live_workers_reuse_a_bounded_number_of_connections(self, tmp_path: Path, monkeypatch) -> None:
        from concurrent.futures import ThreadPoolExecutor

        connect = sqlite3.connect
        connections = []

        def open_connection(*args, **kwargs):
            conn = connect(*args, **kwargs)
            connections.append(conn)
            return conn

        monkeypatch.setattr(sqlite3, "connect", open_connection)
        backend = SqliteMemoryBackend(namespace="bounded", db_path=tmp_path / "bounded.sqlite")
        barrier = threading.Barrier(12)

        def worker():
            barrier.wait(timeout=5)
            for _ in range(20):
                assert backend.list_raw(limit=1) == []

        try:
            with ThreadPoolExecutor(max_workers=12) as pool:
                futures = [pool.submit(worker) for _ in range(12)]
                for future in futures:
                    future.result(timeout=10)
                assert len(connections) <= 2
        finally:
            backend.close()
        for conn in connections:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                conn.execute("SELECT 1")

    def test_close_waits_for_an_active_transaction(self, backend: SqliteMemoryBackend) -> None:
        entered, release, closing, closed = (threading.Event() for _ in range(4))

        def transaction():
            with backend.transaction():
                entered.set()
                assert release.wait(timeout=5)
                backend.set_meta("committed", "yes")

        def close():
            closing.set()
            backend.close()
            closed.set()

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(transaction)
            assert entered.wait(timeout=5)
            shutdown = pool.submit(close)
            assert closing.wait(timeout=5)
            try:
                assert not closed.wait(timeout=0.05)
            finally:
                release.set()
            pending.result(timeout=5)
            shutdown.result(timeout=5)
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            backend.get_meta("committed")


posix_only = pytest.mark.skipif(
    not os.path.isdir("/proc"),
    reason="counts fds via /proc",
)


@posix_only
class TestShortLivedThreadsDoNotLeakFds:
    def test_300_short_lived_threads_leave_fds_flat(self, tmp_path: Path) -> None:
        """Regression for Octop#1339: glibc reuses idents, so every
        short-lived worker thread used to leak one database fd."""
        db_path = tmp_path / "probe.sqlite"
        backend = SqliteMemoryBackend(namespace="probe", db_path=db_path)

        def db_fds() -> int:
            prefix = str(db_path)
            count = 0
            for fd in os.listdir(f"/proc/{os.getpid()}/fd"):
                try:
                    if os.readlink(f"/proc/{os.getpid()}/fd/{fd}").startswith(prefix):
                        count += 1
                except OSError:
                    pass
            return count

        baseline = db_fds()

        def work() -> None:
            backend.list_raw(limit=1)

        for _ in range(300):
            t = threading.Thread(target=work, daemon=True)
            t.start()
            t.join()

        assert db_fds() <= baseline + 4
        backend.close()
