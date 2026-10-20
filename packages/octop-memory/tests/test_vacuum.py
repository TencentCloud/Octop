"""Tests for pipeline.lifecycle.vacuum (RISK-026 / ADR-025).

SQLite tests always run. Postgres tests follow the same skip pattern as
test_postgres.py: skipped when psycopg isn't installed or the database
is unreachable, since ``VACUUM``/autovacuum behavior can't be
meaningfully mocked.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.lifecycle.vacuum import (
    DEFAULT_INCREMENTAL_VACUUM_PAGES,
    check_storage,
    compact_vacuum,
    nudge_vacuum,
)
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import JournalEntry

# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------


def _freelist_count(memory: Memory) -> int:
    backend = memory.backend
    assert isinstance(backend, SqliteMemoryBackend)
    row = backend._conn.execute("PRAGMA freelist_count").fetchone()
    assert row is not None
    return int(row[0])


def _memory(tmp_path: Path, name: str) -> Memory:
    backend = SqliteMemoryBackend(namespace=name, db_path=tmp_path / f"{name}.sqlite")
    return Memory(namespace=name, backend=backend)


def _legacy_none_memory(tmp_path: Path, name: str) -> Memory:
    """Pre-ADR-027 database: tables exist with auto_vacuum=NONE.

    Opening via SqliteMemoryBackend sets the INCREMENTAL pragma, but the
    mode does not take effect until VACUUM — same as a stock user DB.
    """
    path = tmp_path / f"{name}.sqlite"
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA auto_vacuum=NONE")
        conn.execute("CREATE TABLE _pre_existing (x INTEGER)")
        conn.commit()
    finally:
        conn.close()
    return _memory(tmp_path, name)


def _bloat_then_delete_journal(memory: Memory, *, rows: int = 3000) -> None:
    """Insert `rows` journal entries with a fat note, then delete them all —
    the standard "create freed pages" fixture for these tests."""
    ns = memory.backend._ns  # type: ignore[attr-defined]
    conn = memory.backend._conn  # type: ignore[attr-defined]
    for _ in range(rows):
        entry = JournalEntry(
            id=str(uuid.uuid4()), timestamp=datetime.now(UTC), action="extract_run", actor="auto", note="x" * 500
        )
        memory.backend.append_journal(entry)  # type: ignore[attr-defined]
    conn.execute(f"DELETE FROM {ns}_journal")
    conn.commit()


class TestSqliteNudgeVacuum:
    def test_noop_and_reports_auto_vacuum_disabled(self, tmp_path: Path) -> None:
        memory = _legacy_none_memory(tmp_path, "nudge_disabled")
        _bloat_then_delete_journal(memory)

        stats = nudge_vacuum(memory)

        assert stats.backend == "sqlite"
        assert stats.auto_vacuum_enabled is False
        assert stats.pages_reclaimed == 0
        assert stats.freelist_pages_before and stats.freelist_pages_before > 0

    def test_new_db_reclaims_without_compact(self, tmp_path: Path) -> None:
        """P0: a file created today is already INCREMENTAL."""
        memory = _memory(tmp_path, "nudge_new")
        assert memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2  # type: ignore[attr-defined]
        _bloat_then_delete_journal(memory)

        stats = nudge_vacuum(memory)

        assert stats.auto_vacuum_enabled is True
        assert stats.pages_reclaimed > 0

    def test_dry_run_predicts_exactly_and_changes_nothing(self, tmp_path: Path) -> None:
        """dry_run must PREDICT the real outcome, not report a bare 0.

        The prediction is exact rather than an estimate: a real call
        reclaims one page per loop iteration until the budget or the
        freelist runs out, so min() is the true answer.
        """
        memory = _memory(tmp_path, "nudge_dry_run")
        compact_vacuum(memory)  # bootstrap auto_vacuum=INCREMENTAL
        _bloat_then_delete_journal(memory)
        freelist_before = _freelist_count(memory)
        assert freelist_before > 5, "fixture must free more pages than the small budget below"

        predicted = nudge_vacuum(memory, pages=5, dry_run=True)

        assert predicted.dry_run is True
        assert predicted.pages_reclaimed == 5  # min(budget=5, freelist)
        freelist_after = _freelist_count(memory)
        assert freelist_after == freelist_before, "dry_run must not touch anything"

        # The prediction matches what a real run actually does.
        actual = nudge_vacuum(memory, pages=5)
        assert actual.pages_reclaimed == predicted.pages_reclaimed

    def test_dry_run_prediction_is_capped_by_freelist_not_budget(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "nudge_dry_small_freelist")
        compact_vacuum(memory)
        _bloat_then_delete_journal(memory, rows=50)
        freelist_before = _freelist_count(memory)

        predicted = nudge_vacuum(memory, pages=10_000, dry_run=True)

        assert predicted.pages_reclaimed == freelist_before  # freelist is the binding limit

    def test_reclaims_freed_pages_and_shrinks_file(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "nudge_reclaim")
        compact_vacuum(memory)
        _bloat_then_delete_journal(memory)
        freelist_before = _freelist_count(memory)
        assert freelist_before > 0

        stats = nudge_vacuum(memory, pages=DEFAULT_INCREMENTAL_VACUUM_PAGES * 10)

        assert stats.auto_vacuum_enabled is True
        assert stats.pages_reclaimed == freelist_before
        freelist_after = _freelist_count(memory)
        assert freelist_after == 0

    def test_pages_argument_bounds_a_single_call(self, tmp_path: Path) -> None:
        """Regression test: PRAGMA incremental_vacuum(N) via Python's sqlite3
        module only reclaims one page per execute() regardless of N — the
        bounded-page-count contract has to come from vacuum.py's own loop,
        not from trusting the pragma argument. See vacuum.py's comment."""
        memory = _memory(tmp_path, "nudge_bounded")
        compact_vacuum(memory)
        _bloat_then_delete_journal(memory)
        freelist_before = _freelist_count(memory)
        assert freelist_before > 5, "fixture must free more pages than the small budget below"

        stats = nudge_vacuum(memory, pages=5)

        assert stats.pages_reclaimed == 5
        freelist_after = _freelist_count(memory)
        assert freelist_after == freelist_before - 5

    def test_does_not_commit_a_callers_open_transaction(self, tmp_path: Path) -> None:
        """nudge_vacuum must not disturb an in-flight transaction.

        It is designed to run from a host's background idle timer while the
        agent may be mid-write, and SqliteMemoryBackend shares one
        check_same_thread=False connection whose transaction() context
        manager keeps multi-table writes atomic (RISK-013).

        This pins the reason vacuum.py loops over incremental_vacuum(1)
        instead of calling executescript("PRAGMA incremental_vacuum(N)"),
        which honours the page budget in one call and is slightly faster but
        issues an implicit COMMIT first. Swapping the loop for executescript
        makes this test fail.
        """
        memory = _memory(tmp_path, "nudge_txn_safe")
        compact_vacuum(memory)
        _bloat_then_delete_journal(memory)
        conn = memory.backend._conn  # type: ignore[attr-defined]
        ns = memory.backend._ns  # type: ignore[attr-defined]

        # Open a write transaction and leave it uncommitted.
        conn.execute(
            f"INSERT INTO {ns}_journal (id, timestamp, action, actor, note) VALUES (?, ?, ?, ?, ?)",
            ("pending-row", datetime.now(UTC).isoformat(), "extract_run", "auto", "uncommitted"),
        )
        assert conn.in_transaction

        stats = nudge_vacuum(memory, pages=5)

        assert conn.in_transaction, "nudge_vacuum must not commit the caller's transaction"
        # The skip must be reported, not silently look like "nothing to reclaim":
        # the freelist is non-empty, so a bare pages_reclaimed=0 would mislead.
        assert stats.skipped_reason is not None
        assert stats.pages_reclaimed == 0
        assert stats.freelist_pages_before and stats.freelist_pages_before > 0
        # And the row must still be invisible to any other connection.
        other = sqlite3.connect(str(memory.backend._db_path))  # type: ignore[attr-defined]
        try:
            visible = other.execute(f"SELECT COUNT(*) FROM {ns}_journal WHERE id = 'pending-row'").fetchone()[0]
        finally:
            other.close()
        assert visible == 0, "uncommitted row leaked — something issued an implicit COMMIT"
        conn.rollback()


class TestSqliteCompactVacuum:
    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "compact_dry_run")
        _bloat_then_delete_journal(memory)
        mode_before = memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0]  # type: ignore[attr-defined]

        stats = compact_vacuum(memory, dry_run=True)

        assert stats.dry_run is True
        assert stats.file_size_before == stats.file_size_after
        mode_after = memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0]  # type: ignore[attr-defined]
        assert mode_after == mode_before  # dry-run bootstraps nothing

    def test_bootstraps_incremental_mode_and_shrinks_file(self, tmp_path: Path) -> None:
        memory = _legacy_none_memory(tmp_path, "compact_bootstrap")
        assert memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 0  # type: ignore[attr-defined]
        _bloat_then_delete_journal(memory)

        stats = compact_vacuum(memory)

        assert stats.auto_vacuum_was_enabled is True
        assert stats.file_size_before is not None
        assert stats.file_size_after is not None
        assert stats.file_size_after < stats.file_size_before
        mode_after = memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0]  # type: ignore[attr-defined]
        assert mode_after == 2  # INCREMENTAL

    def test_second_call_is_a_plain_periodic_compaction(self, tmp_path: Path) -> None:
        """Once bootstrapped, later calls just compact — no re-bootstrap needed."""
        memory = _memory(tmp_path, "compact_repeat")
        compact_vacuum(memory)
        _bloat_then_delete_journal(memory)

        stats = compact_vacuum(memory)

        assert stats.auto_vacuum_was_enabled is True
        assert stats.file_size_after < stats.file_size_before  # type: ignore[operator]


class TestSqliteCheckStorage:
    """`check_storage` is the read-only inspection entry point (ADR-025)."""

    def test_reports_waste_and_never_mutates(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "check_waste")
        compact_vacuum(memory)
        _bloat_then_delete_journal(memory)
        freelist_before = _freelist_count(memory)

        check = check_storage(memory)

        assert check.backend == "sqlite"
        assert check.auto_vacuum_enabled is True
        assert check.freelist_pages == freelist_before
        assert check.page_size and check.page_size > 0
        assert check.reclaimable_bytes == freelist_before * check.page_size
        assert check.file_size and check.file_size > 0
        # Nothing moved.
        freelist_after = _freelist_count(memory)
        assert freelist_after == freelist_before

    def test_would_reclaim_matches_what_vacuum_actually_does(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "check_predicts")
        compact_vacuum(memory)
        _bloat_then_delete_journal(memory)

        predicted = check_storage(memory).would_reclaim_pages
        actual = nudge_vacuum(memory).pages_reclaimed

        assert predicted == actual

    def test_recommends_compact_when_auto_vacuum_is_off(self, tmp_path: Path) -> None:
        memory = _legacy_none_memory(tmp_path, "check_needs_bootstrap")
        _bloat_then_delete_journal(memory)

        check = check_storage(memory)

        assert check.auto_vacuum_enabled is False
        # Honest: a nudge can't reclaim anything yet, and the report says why.
        assert check.would_reclaim_pages == 0
        assert check.freelist_pages and check.freelist_pages > 0
        assert any("compact" in r for r in check.recommendations)

    def test_clean_store_has_no_recommendations(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "check_clean")
        compact_vacuum(memory)  # bootstrap + compact leaves nothing to reclaim

        check = check_storage(memory)

        assert check.freelist_pages == 0
        assert check.would_reclaim_pages == 0
        assert check.recommendations == []


class TestUnsupportedBackend:
    def test_nudge_vacuum_raises_for_unknown_backend(self) -> None:
        class _FakeMemory:
            _backend = object()

        with pytest.raises(RuntimeError, match="unsupported backend"):
            nudge_vacuum(_FakeMemory())  # type: ignore[arg-type]

    def test_check_storage_raises_for_unknown_backend(self) -> None:
        class _FakeMemory:
            _backend = object()

        with pytest.raises(RuntimeError, match="unsupported backend"):
            check_storage(_FakeMemory())  # type: ignore[arg-type]

    def test_compact_vacuum_raises_for_unknown_backend(self) -> None:
        class _FakeMemory:
            _backend = object()

        with pytest.raises(RuntimeError, match="unsupported backend"):
            compact_vacuum(_FakeMemory())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

try:
    import psycopg  # noqa: F401 — availability probe

    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False

pytestmark_pg = pytest.mark.skipif(not PG_AVAILABLE, reason="psycopg not installed")

PG_DSN = os.environ.get("TEST_POSTGRES_DSN", "postgresql://localhost/octop_memory_test")


def _pg_memory(ns: str) -> Memory:
    from octop_memory.storage.backends.postgres import PostgresMemoryBackend

    backend = PostgresMemoryBackend(namespace=ns, dsn=PG_DSN)
    return Memory(namespace=ns, backend=backend)


@pytestmark_pg
@pytest.mark.usefixtures("postgres_dsn")
class TestPostgresNudgeVacuum:
    def test_journal_is_vacuumed_checkpoint_tables_skip_or_vacuum(self) -> None:
        ns = f"test_vacuum_{uuid.uuid4().hex[:12]}"
        memory = _pg_memory(ns)
        try:
            stats = nudge_vacuum(memory)

            assert stats.backend == "postgres"
            by_table = {t.table: t for t in stats.tables}
            assert by_table["octop_memory.journal"].action == "VACUUM"
            assert by_table["octop_memory.journal"].skipped_reason is None
            # checkpoint tables are third-party (LangGraph) and only exist
            # if some checkpointer has run against this database before —
            # either outcome (skip / vacuumed) is valid, just must be one
            # of the two, not an error.
            for table in ("public.checkpoints", "public.checkpoint_blobs", "public.checkpoint_writes"):
                result = by_table[table]
                assert result.action in ("VACUUM", "skip")
        finally:
            memory.backend.purge_namespace()  # type: ignore[attr-defined]
            memory.backend.close()  # type: ignore[attr-defined]

    def test_dry_run_reports_would_run_without_vacuuming(self) -> None:
        ns = f"test_vacuum_{uuid.uuid4().hex[:12]}"
        memory = _pg_memory(ns)
        try:
            stats = nudge_vacuum(memory, dry_run=True)

            assert stats.dry_run is True
            journal_result = next(t for t in stats.tables if t.table == "octop_memory.journal")
            assert journal_result.action == "would run VACUUM"
        finally:
            memory.backend.purge_namespace()  # type: ignore[attr-defined]
            memory.backend.close()  # type: ignore[attr-defined]


@pytestmark_pg
@pytest.mark.usefixtures("postgres_dsn")
class TestPostgresCompactVacuum:
    def test_full_vacuum_runs_on_journal(self) -> None:
        ns = f"test_compact_{uuid.uuid4().hex[:12]}"
        memory = _pg_memory(ns)
        try:
            stats = compact_vacuum(memory)

            assert stats.backend == "postgres"
            journal_result = next(t for t in stats.tables if t.table == "octop_memory.journal")
            assert journal_result.action == "VACUUM FULL"
        finally:
            memory.backend.purge_namespace()  # type: ignore[attr-defined]
            memory.backend.close()  # type: ignore[attr-defined]


@pytestmark_pg
@pytest.mark.usefixtures("postgres_dsn")
class TestPostgresCheckStorage:
    def test_reports_per_table_dead_tuples_without_mutating(self) -> None:
        ns = f"test_check_{uuid.uuid4().hex[:12]}"
        memory = _pg_memory(ns)
        try:
            check = check_storage(memory)

            assert check.backend == "postgres"
            # SQLite-only fields stay unset rather than being faked.
            assert check.freelist_pages is None
            assert check.page_size is None

            by_table = {t.table: t for t in check.tables}
            assert "octop_memory.journal" in by_table
            journal = by_table["octop_memory.journal"]
            assert journal.exists is True
            assert journal.dead_tuples is not None
            assert journal.live_tuples is not None
            for table in ("public.checkpoints", "public.checkpoint_blobs", "public.checkpoint_writes"):
                assert table in by_table
        finally:
            memory.backend.purge_namespace()  # type: ignore[attr-defined]
            memory.backend.close()  # type: ignore[attr-defined]
