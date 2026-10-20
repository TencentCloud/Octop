"""Tests for maybe_bootstrap_incremental (ADR-027 P2)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.lifecycle.maintenance import maybe_bootstrap_incremental
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend


def _memory(tmp_path: Path, name: str) -> Memory:
    backend = SqliteMemoryBackend(namespace=name, db_path=tmp_path / f"{name}.sqlite")
    return Memory(namespace=name, backend=backend)


def _legacy_none_memory(tmp_path: Path, name: str) -> Memory:
    path = tmp_path / f"{name}.sqlite"
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA auto_vacuum=NONE")
        conn.execute("CREATE TABLE _pre_existing (x INTEGER)")
        conn.commit()
    finally:
        conn.close()
    return _memory(tmp_path, name)


class TestMaybeBootstrapIncremental:
    def test_new_db_already_incremental(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "boot_new")

        stats = maybe_bootstrap_incremental(memory, window="idle")

        assert stats.skipped_reason == "already_incremental"
        assert stats.did_compact is False
        assert stats.finished is True
        assert memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2  # type: ignore[attr-defined]

    def test_legacy_none_compacts_on_idle(self, tmp_path: Path) -> None:
        memory = _legacy_none_memory(tmp_path, "boot_legacy")
        assert memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 0  # type: ignore[attr-defined]

        stats = maybe_bootstrap_incremental(memory, window="idle")

        assert stats.did_compact is True
        assert stats.finished is True
        assert stats.compact is not None
        assert memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2  # type: ignore[attr-defined]

    def test_idle_defers_over_soft_limit(self, tmp_path: Path) -> None:
        memory = _legacy_none_memory(tmp_path, "boot_soft")

        stats = maybe_bootstrap_incremental(memory, window="idle", soft_limit_bytes=1, hard_limit_bytes=10**9)

        assert stats.skipped_reason == "need_stronger_window"
        assert stats.did_compact is False
        assert stats.finished is False
        assert memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 0  # type: ignore[attr-defined]

    def test_startup_allows_over_soft_limit(self, tmp_path: Path) -> None:
        memory = _legacy_none_memory(tmp_path, "boot_startup")

        stats = maybe_bootstrap_incremental(memory, window="startup", soft_limit_bytes=1, hard_limit_bytes=10**9)

        assert stats.did_compact is True
        assert memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2  # type: ignore[attr-defined]

    def test_explicit_hard_limit_never_compacts(self, tmp_path: Path) -> None:
        memory = _legacy_none_memory(tmp_path, "boot_hard")

        stats = maybe_bootstrap_incremental(memory, window="startup", soft_limit_bytes=1, hard_limit_bytes=1)

        assert stats.skipped_reason == "over_hard_limit"
        assert stats.finished is True
        assert memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 0  # type: ignore[attr-defined]

    def test_startup_has_no_default_size_cap(self, tmp_path: Path) -> None:
        memory = _legacy_none_memory(tmp_path, "boot_uncapped")

        stats = maybe_bootstrap_incremental(memory, window="startup", soft_limit_bytes=1)

        assert stats.did_compact is True
        assert stats.skipped_reason is None
        assert memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2  # type: ignore[attr-defined]

    def test_insufficient_disk_is_retryable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        memory = _legacy_none_memory(tmp_path, "boot_disk")

        monkeypatch.setattr(
            "octop_memory.pipeline.lifecycle.maintenance._disk_free_bytes",
            lambda _path: 1,
        )

        stats = maybe_bootstrap_incremental(memory, window="startup", disk_margin_bytes=10**9)

        assert stats.skipped_reason == "insufficient_disk"
        assert stats.finished is False
        assert stats.did_compact is False
        assert memory.backend._conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 0  # type: ignore[attr-defined]

    def test_unknown_window_raises(self, tmp_path: Path) -> None:
        memory = _memory(tmp_path, "boot_bad_window")
        with pytest.raises(ValueError, match="unknown window"):
            maybe_bootstrap_incremental(memory, window="nightly")

    def test_not_sqlite(self) -> None:
        class _Fake:
            _backend = object()

        stats = maybe_bootstrap_incremental(_Fake(), window="idle")  # type: ignore[arg-type]
        assert stats.skipped_reason == "not_sqlite"
        assert stats.finished is True

    def test_compact_error_is_retryable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        memory = _legacy_none_memory(tmp_path, "boot_err")

        def boom(_memory: object) -> None:
            raise RuntimeError("locked")

        monkeypatch.setattr(
            "octop_memory.pipeline.lifecycle.maintenance.compact_vacuum",
            boom,
        )

        stats = maybe_bootstrap_incremental(memory, window="idle")

        assert stats.error is not None
        assert "locked" in stats.error
        assert stats.finished is False
        assert stats.did_compact is False
