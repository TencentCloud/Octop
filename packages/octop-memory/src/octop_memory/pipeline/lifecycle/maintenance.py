"""Host-callable idle maintenance — prune + GC + nudge + one-shot bootstrap.

RISK-026's cleanup primitives were CLI-only. Hosts (octop-harness
``MemoryMiddleware``) call :func:`run_idle_maintenance` from an idle /
interval timer so everyday slimming does not need a user or an ops cron.

Each cheap step is fail-soft for driver, I/O, and payload errors: one failure is
logged on the returned stats and the remaining steps still run. Other
exceptions propagate. :func:`compact_vacuum` is
**not** in the cheap pass (ADR-025). New SQLite files start at
``auto_vacuum=INCREMENTAL`` so :func:`nudge_vacuum` can reclaim without
a bootstrap. Legacy NONE databases use :func:`maybe_bootstrap_incremental`
once, from a confirmed idle / startup window (ADR-027 P2).
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from octop_memory.pipeline.lifecycle.checkpoint_gc import (
    DEFAULT_KEEP_LAST_CHECKPOINTS,
    CheckpointGcStats,
    prune_checkpoints,
)
from octop_memory.pipeline.lifecycle.gc import GcStats, run_gc
from octop_memory.pipeline.lifecycle.vacuum import (
    MAINTENANCE_INCREMENTAL_VACUUM_PAGES,
    CompactStats,
    VacuumStats,
    check_storage,
    compact_vacuum,
    nudge_vacuum,
)
from octop_memory.storage.driver_errors import REPORTABLE_ERRORS

if TYPE_CHECKING:
    from octop_memory.core import Memory

_LOG = logging.getLogger(__name__)

BOOTSTRAP_WINDOWS = frozenset({"idle", "long_idle", "startup"})
DEFAULT_BOOTSTRAP_SOFT_BYTES = 200 * 1024 * 1024
"""Idle-window cap. Larger NONE files wait for startup / long_idle."""
DEFAULT_BOOTSTRAP_HARD_BYTES: int | None = None
"""Optional size cap for startup / long_idle. ``None`` = no cap (ADR-027).

An explicit integer is for tests / ops overrides. Short idle still uses
``soft_limit_bytes`` only.
"""
DEFAULT_BOOTSTRAP_DISK_MARGIN_BYTES = 64 * 1024 * 1024
"""Extra free disk beyond current file+WAL before we attempt VACUUM."""
DEFAULT_WAL_TRUNCATE_BYTES = 2 * 1024 * 1024
"""Idle TRUNCATE only when ``-wal`` is at least this big (ADR-027 P3).

2MB sits under the 3-4MB WAL high-water we saw after compact, and
above tiny leftover WAL files that are not worth blocking writers for.
"""


@dataclass
class IdleMaintenanceStats:
    """Outcome of one :func:`run_idle_maintenance` tick."""

    prune: CheckpointGcStats | None = None
    gc: GcStats | None = None
    vacuum: VacuumStats | None = None
    prune_error: str | None = None
    gc_error: str | None = None
    vacuum_error: str | None = None


def run_idle_maintenance(
    memory: Memory,
    *,
    include_orphan_raw: bool = True,
    drop_subgraph_streams: bool = False,
) -> IdleMaintenanceStats:
    """Run one cheap prune → GC → nudge pass. Safe with live traffic.

    Does not raise. Checkpointer / backend gaps (no langgraph extra,
    Postgres prune not implemented) land in ``*_error`` and the rest of
    the tick continues.

    ``include_orphan_raw=False`` skips the orphan-raw pass (startup can
    opt out if a host wants the shortest path to VACUUM).

    ``drop_subgraph_streams=True`` deletes finished ``tools:*`` streams
    (in-flight / HITL threads are skipped). Hosts should pass this only
    from a quiet window or after a completed turn; the default stays
    off so a live-traffic tick only trims each stream to ``keep_last``.
    """
    stats = IdleMaintenanceStats()

    try:
        stats.prune = prune_checkpoints(
            memory,
            keep_last=DEFAULT_KEEP_LAST_CHECKPOINTS,
            drop_subgraph_streams=drop_subgraph_streams,
        )
    except REPORTABLE_ERRORS as exc:
        stats.prune_error = f"{type(exc).__name__}: {exc}"
        _LOG.warning("idle maintenance: prune_checkpoints failed", exc_info=True)

    try:
        stats.gc = run_gc(memory, include_orphan_raw=include_orphan_raw)
    except REPORTABLE_ERRORS as exc:
        stats.gc_error = f"{type(exc).__name__}: {exc}"
        _LOG.warning("idle maintenance: run_gc failed", exc_info=True)

    try:
        stats.vacuum = nudge_vacuum(memory, pages=MAINTENANCE_INCREMENTAL_VACUUM_PAGES)
    except REPORTABLE_ERRORS as exc:
        stats.vacuum_error = f"{type(exc).__name__}: {exc}"
        _LOG.warning("idle maintenance: nudge_vacuum failed", exc_info=True)

    return stats


@dataclass
class BootstrapStats:
    """Outcome of one :func:`maybe_bootstrap_incremental` attempt."""

    window: str
    skipped_reason: str | None = None
    compact: CompactStats | None = None
    error: str | None = None
    file_bytes: int | None = None
    free_bytes: int | None = None

    @property
    def did_compact(self) -> bool:
        return self.compact is not None and self.skipped_reason is None and self.error is None

    @property
    def finished(self) -> bool:
        """True when the host should stop retrying this process.

        ``need_stronger_window`` / ``busy`` / errors stay retryable.
        """
        return (
            self.skipped_reason
            in {
                "already_incremental",
                "not_sqlite",
                "over_hard_limit",
            }
            or self.did_compact
        )


def _disk_free_bytes(path: Path) -> int:
    return int(shutil.disk_usage(path).free)


def maybe_bootstrap_incremental(
    memory: Memory,
    *,
    window: str,
    soft_limit_bytes: int = DEFAULT_BOOTSTRAP_SOFT_BYTES,
    hard_limit_bytes: int | None = DEFAULT_BOOTSTRAP_HARD_BYTES,
    disk_margin_bytes: int = DEFAULT_BOOTSTRAP_DISK_MARGIN_BYTES,
) -> BootstrapStats:
    """One-shot compact to flip a legacy NONE SQLite file to INCREMENTAL.

    Does not raise. Hosts must only call this from a confirmed idle or
    startup-with-no-traffic window — this function enforces size / disk
    gates, not "is anyone chatting".

    Windows:

    * ``idle`` — short quiet; only files ≤ ``soft_limit_bytes``.
    * ``startup`` / ``long_idle`` — no default size cap (update restart
      is the intended window). Skip with ``insufficient_disk`` when free
      space is below file+WAL + ``disk_margin_bytes`` (retryable).
    * ``hard_limit_bytes`` is an optional override; above it
      ``over_hard_limit`` and the host should stop retrying.
    """
    if window not in BOOTSTRAP_WINDOWS:
        raise ValueError(f"maybe_bootstrap_incremental: unknown window {window!r}")
    if soft_limit_bytes < 1:
        raise ValueError("soft_limit_bytes must be >= 1")
    if disk_margin_bytes < 0:
        raise ValueError("disk_margin_bytes must be >= 0")
    if hard_limit_bytes is not None:
        if hard_limit_bytes < 1:
            raise ValueError("hard_limit_bytes must be >= 1 when set")
        if soft_limit_bytes > hard_limit_bytes:
            raise ValueError("soft_limit_bytes must be <= hard_limit_bytes")

    stats = BootstrapStats(window=window)
    from octop_memory.storage.backends.sqlite import SqliteMemoryBackend

    backend = getattr(memory, "_backend", None)
    if not isinstance(backend, SqliteMemoryBackend):
        stats.skipped_reason = "not_sqlite"
        return stats

    try:
        check = check_storage(memory)
    except REPORTABLE_ERRORS as exc:
        stats.error = f"{type(exc).__name__}: {exc}"
        _LOG.warning("bootstrap: check_storage failed", exc_info=True)
        return stats

    if check.auto_vacuum_enabled:
        stats.skipped_reason = "already_incremental"
        stats.file_bytes = (check.file_size or 0) + (check.wal_size or 0)
        return stats

    size = (check.file_size or 0) + (check.wal_size or 0)
    stats.file_bytes = size
    if hard_limit_bytes is not None and size > hard_limit_bytes:
        stats.skipped_reason = "over_hard_limit"
        return stats
    if size > soft_limit_bytes and window == "idle":
        stats.skipped_reason = "need_stronger_window"
        return stats

    try:
        stats.free_bytes = _disk_free_bytes(backend._db_path.parent)
    except OSError as exc:
        stats.error = f"{type(exc).__name__}: {exc}"
        _LOG.warning("bootstrap: disk_usage failed", exc_info=True)
        return stats
    needed = size + disk_margin_bytes
    if stats.free_bytes < needed:
        stats.skipped_reason = "insufficient_disk"
        _LOG.warning(
            "bootstrap: insufficient disk window=%s file_bytes=%s free_bytes=%s needed=%s",
            window,
            size,
            stats.free_bytes,
            needed,
        )
        return stats

    try:
        stats.compact = compact_vacuum(memory)
    except REPORTABLE_ERRORS as exc:
        stats.error = f"{type(exc).__name__}: {exc}"
        _LOG.warning("bootstrap: compact_vacuum failed window=%s", window, exc_info=True)
    return stats


@dataclass
class WalTruncateStats:
    """Outcome of one :func:`maybe_truncate_wal` attempt."""

    skipped_reason: str | None = None
    wal_bytes_before: int | None = None
    wal_bytes_after: int | None = None
    busy: int | None = None
    log: int | None = None
    checkpointed: int | None = None
    error: str | None = None

    @property
    def did_truncate(self) -> bool:
        return (
            self.skipped_reason is None
            and self.error is None
            and self.busy == 0
            and self.wal_bytes_after is not None
            and self.wal_bytes_before is not None
            and self.wal_bytes_after < self.wal_bytes_before
        )


def maybe_truncate_wal(
    memory: Memory,
    *,
    min_wal_bytes: int = DEFAULT_WAL_TRUNCATE_BYTES,
) -> WalTruncateStats:
    """Idle-only ``wal_checkpoint(TRUNCATE)`` when the WAL file is large.

    Hosts must call this from a confirmed idle window — TRUNCATE can
    block writers. Below ``min_wal_bytes`` this is a no-op so small WALs
    are left to the PASSIVE checkpoint inside :func:`nudge_vacuum`.
    """
    if min_wal_bytes < 1:
        raise ValueError("min_wal_bytes must be >= 1")

    stats = WalTruncateStats()
    from octop_memory.storage.backends.sqlite import SqliteMemoryBackend

    backend = getattr(memory, "_backend", None)
    if not isinstance(backend, SqliteMemoryBackend):
        stats.skipped_reason = "not_sqlite"
        return stats

    wal_path = backend._db_path.with_name(backend._db_path.name + "-wal")
    before = wal_path.stat().st_size if wal_path.exists() else 0
    stats.wal_bytes_before = before
    if before < min_wal_bytes:
        stats.skipped_reason = "below_threshold"
        stats.wal_bytes_after = before
        return stats

    with backend._conn_lock:
        conn = backend._conn
        if conn.in_transaction:
            stats.skipped_reason = "in_transaction"
            stats.wal_bytes_after = before
            return stats

        try:
            row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        except REPORTABLE_ERRORS as exc:
            stats.error = f"{type(exc).__name__}: {exc}"
            _LOG.warning("wal truncate failed", exc_info=True)
            stats.wal_bytes_after = wal_path.stat().st_size if wal_path.exists() else 0
            return stats

        if row is not None:
            stats.busy, stats.log, stats.checkpointed = int(row[0]), int(row[1]), int(row[2])
        after = wal_path.stat().st_size if wal_path.exists() else 0
        stats.wal_bytes_after = after
        if stats.busy:
            stats.skipped_reason = "busy"
        return stats


__all__ = [
    "BOOTSTRAP_WINDOWS",
    "DEFAULT_BOOTSTRAP_DISK_MARGIN_BYTES",
    "DEFAULT_BOOTSTRAP_HARD_BYTES",
    "DEFAULT_BOOTSTRAP_SOFT_BYTES",
    "DEFAULT_WAL_TRUNCATE_BYTES",
    "BootstrapStats",
    "IdleMaintenanceStats",
    "WalTruncateStats",
    "maybe_bootstrap_incremental",
    "maybe_truncate_wal",
    "run_idle_maintenance",
]
