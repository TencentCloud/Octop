"""Tests for pipeline.lifecycle.maintenance (ADR-027 idle tick)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.lifecycle.maintenance import maybe_truncate_wal, run_idle_maintenance
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import JournalEntry


def _memory(tmp_path: Path, name: str) -> Memory:
    backend = SqliteMemoryBackend(namespace=name, db_path=tmp_path / f"{name}.sqlite")
    return Memory(namespace=name, backend=backend)


class TestRunIdleMaintenance:
    def test_drop_subgraph_flag_reaches_prune(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        memory = _memory(tmp_path, "idle_drop")
        seen: dict[str, object] = {}

        def _capture(_memory: object, **kwargs: object) -> object:
            seen.update(kwargs)
            from octop_memory.pipeline.lifecycle.checkpoint_gc import CheckpointGcStats

            return CheckpointGcStats()

        monkeypatch.setattr(
            "octop_memory.pipeline.lifecycle.maintenance.prune_checkpoints",
            _capture,
        )
        run_idle_maintenance(memory, drop_subgraph_streams=True)
        assert seen.get("drop_subgraph_streams") is True
        assert seen.get("keep_last") == 1

    def test_empty_new_db_runs_all_steps(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "idle_empty")

        stats = run_idle_maintenance(memory)

        assert stats.prune_error is None
        assert stats.gc_error is None
        assert stats.vacuum_error is None
        assert stats.prune is not None
        assert stats.gc is not None
        assert stats.vacuum is not None
        assert stats.vacuum.auto_vacuum_enabled is True
        assert stats.prune.checkpoints_deleted == 0
        assert stats.gc.total_deleted == 0

    def test_can_skip_orphan_raw_pass(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "idle_skip_orphan")
        stats = run_idle_maintenance(memory, include_orphan_raw=False)
        assert stats.gc is not None
        assert stats.gc.orphan_raw_events_deleted == 0

    def test_expires_old_pipeline_journal(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "idle_journal")
        old = datetime(2020, 1, 1, tzinfo=UTC)
        memory.backend.append_journal(  # type: ignore[attr-defined]
            JournalEntry(
                id="old-run",
                timestamp=old,
                action="extract_run",
                actor="auto",
                note="stale",
            )
        )
        memory.append_journal(
            JournalEntry(
                id="keep-promote",
                timestamp=old,
                action="promote",
                actor="auto",
                note="decision",
            )
        )

        stats = run_idle_maintenance(memory)

        assert stats.gc is not None
        assert stats.gc.journal_rows_deleted == 1
        notes = {row.note for row in memory.list_journal(limit=10)}
        assert notes == {"decision"}

    def test_continues_after_prune_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        memory = _memory(tmp_path, "idle_soft")

        def boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("no checkpointer")

        monkeypatch.setattr(
            "octop_memory.pipeline.lifecycle.maintenance.prune_checkpoints",
            boom,
        )

        stats = run_idle_maintenance(memory)

        assert stats.prune is None
        assert stats.prune_error is not None
        assert "no checkpointer" in stats.prune_error
        assert stats.gc is not None
        assert stats.gc_error is None
        assert stats.vacuum is not None
        assert stats.vacuum_error is None


class TestMaybeTruncateWal:
    def test_not_sqlite(self) -> None:
        class _Fake:
            _backend = object()

        stats = maybe_truncate_wal(_Fake())  # type: ignore[arg-type]
        assert stats.skipped_reason == "not_sqlite"
        assert stats.did_truncate is False

    def test_below_threshold(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "wal_small")
        stats = maybe_truncate_wal(memory, min_wal_bytes=10**9)
        assert stats.skipped_reason == "below_threshold"
        assert stats.did_truncate is False

    def test_truncates_when_wal_is_large(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "wal_big")
        now = datetime.now(UTC)
        for _ in range(400):
            memory.backend.append_journal(  # type: ignore[attr-defined]
                JournalEntry(
                    id=str(uuid4()),
                    timestamp=now,
                    action="extract_run",
                    actor="auto",
                    note="x" * 2000,
                )
            )
        wal = memory.backend._db_path.with_name(memory.backend._db_path.name + "-wal")  # type: ignore[attr-defined]
        assert wal.exists() and wal.stat().st_size > 1000

        stats = maybe_truncate_wal(memory, min_wal_bytes=1000)

        after = wal.stat().st_size if wal.exists() else 0
        assert stats.busy == 0
        assert stats.error is None
        assert after < stats.wal_bytes_before  # type: ignore[operator]
        assert stats.did_truncate is True

    def test_skips_open_transaction(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "wal_txn")
        now = datetime.now(UTC)
        for _ in range(200):
            memory.backend.append_journal(  # type: ignore[attr-defined]
                JournalEntry(
                    id=str(uuid4()),
                    timestamp=now,
                    action="extract_run",
                    actor="auto",
                    note="y" * 2000,
                )
            )
        conn = memory.backend._conn  # type: ignore[attr-defined]
        conn.execute("BEGIN")
        try:
            stats = maybe_truncate_wal(memory, min_wal_bytes=1)
            assert stats.skipped_reason == "in_transaction"
            assert stats.did_truncate is False
        finally:
            conn.rollback()
