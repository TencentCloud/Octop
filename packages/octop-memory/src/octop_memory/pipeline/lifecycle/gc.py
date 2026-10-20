"""Lifecycle GC for old / dead data (5.6, D47-C cron + CLI).

Implements the cleanup rules from design doc §17 plus journal retention
(ADR-028 / RISK-026 ③):

| Data                                | Retention | Action          |
|-------------------------------------|-----------|-----------------|
| ``rejected`` candidate              | 30 days   | DELETE          |
| ``deprecated`` atom (superseded)    | 90 days   | DELETE          |
| Raw event with no atom referencing it | 180 days | DELETE         |
| Pipeline journal (``extract_run``,  | 14 days   | DELETE          |
| ``gc_*``, ``page_regen*``,          |           | (not journaled) |
| ``consolidate``)                    |           |                 |

Decision journal rows (``promote`` / ``reject`` / ``deprecate`` / ``merge``
/ ``conflict`` / ``entity_merge`` / …) are not expired.

D47-C: both **cron mode** (caller drives a scheduler) and **CLI mode**
(``octop-memory gc run``) call into the same :func:`run_gc` entry point so
the behaviour is identical.

Soft-delete vs hard-delete: design doc called for hard delete *and* a
per-row ``gc_*`` journal. ADR-028 drops the per-row journal — those rows
were feeding the table this pass is supposed to shrink (same reason
checkpoint prune does not journal; ADR-022). ``run_gc`` returns counts
instead.

Each pass is bounded by ``--max-rows`` so a never-run-before namespace
doesn't lock SQLite for minutes when we finally launch the worker.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from octop_memory.core import Memory


# Default retention windows per design doc §17. Override per call as
# needed; tests typically pass tiny windows so synthetic fixtures
# trigger cleanup immediately.
DEFAULT_REJECTED_CANDIDATE_DAYS = 30
DEFAULT_DEPRECATED_ATOM_DAYS = 90
DEFAULT_ORPHAN_RAW_DAYS = 180
DEFAULT_JOURNAL_PIPELINE_DAYS = 14
"""Pipeline / heartbeat journal rows older than this are deleted (ADR-028)."""

PIPELINE_JOURNAL_ACTIONS: tuple[str, ...] = (
    "extract_run",
    "gc_rejected_candidate",
    "gc_deprecated_atom",
    "gc_orphan_raw_event",
    "page_regen",
    "page_regen_failed",
    "consolidate",
)
"""Journal actions that are observability, not a user-facing decision audit."""

DEFAULT_MAX_ROWS_PER_PASS = 500
"""Soft cap so a single GC tick can't lock the DB on a huge backlog.
Caller can run multiple passes if needed."""


@dataclass
class GcStats:
    """Per-action row counts. ``dry_run`` reports what *would* be deleted."""

    rejected_candidates_deleted: int = 0
    deprecated_atoms_deleted: int = 0
    orphan_raw_events_deleted: int = 0
    journal_rows_deleted: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    dry_run: bool = False

    @property
    def total_deleted(self) -> int:
        return (
            self.rejected_candidates_deleted
            + self.deprecated_atoms_deleted
            + self.orphan_raw_events_deleted
            + self.journal_rows_deleted
        )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def run_gc(
    memory: Memory,
    *,
    rejected_candidate_days: int = DEFAULT_REJECTED_CANDIDATE_DAYS,
    deprecated_atom_days: int = DEFAULT_DEPRECATED_ATOM_DAYS,
    orphan_raw_days: int = DEFAULT_ORPHAN_RAW_DAYS,
    journal_pipeline_days: int = DEFAULT_JOURNAL_PIPELINE_DAYS,
    max_rows_per_pass: int = DEFAULT_MAX_ROWS_PER_PASS,
    include_orphan_raw: bool = True,
    dry_run: bool = False,
    now: datetime | None = None,
) -> GcStats:
    """Run one full GC pass over the namespace.

    Four sub-passes execute in this order, each capped by
    ``max_rows_per_pass``:

    1. Rejected candidates older than ``rejected_candidate_days``.
    2. Deprecated atoms older than ``deprecated_atom_days``.
    3. Orphan raw events (no atom references them) older than
       ``orphan_raw_days``. Skipped when ``include_orphan_raw`` is
       false (startup compact — that pass used to load every raw row).
    4. Pipeline journal rows older than ``journal_pipeline_days``.
       This pass does not write journal.

    Set ``dry_run=True`` to count without deleting; useful for the
    ``--dry-run`` CLI mode and for the eval harness.

    Non-SQLite backends (Postgres today) are a no-op: lifecycle SQL is
    still SQLite-only (D46-C / M6). Returning empty stats — instead of
    raising — lets the agent maintenance timer keep ticking without a
    traceback every hour.
    """
    if _sqlite_backend(memory) is None:
        backend = getattr(memory, "_backend", None)
        # DEBUG, not INFO: the host maintenance timer calls this hourly for
        # every agent, and the message is identical each time. The caller
        # already logs the outcome (``memory.maintenance done gc_err=None``),
        # so INFO here only costs ~96 lines/day on a four-agent Postgres host.
        logger.debug(
            "run_gc skipped: backend is not SQLite (got %s; PG GC deferred to M6)",
            type(backend).__name__,
        )
        now_ts = datetime.now(UTC)
        return GcStats(started_at=now_ts, finished_at=now_ts, dry_run=dry_run)
    stats = GcStats(started_at=datetime.now(UTC), dry_run=dry_run)
    cutoff_now = now or datetime.now(UTC)

    cand_cutoff = cutoff_now - timedelta(days=rejected_candidate_days)
    stats.rejected_candidates_deleted = _gc_rejected_candidates(
        memory,
        cutoff=cand_cutoff,
        limit=max_rows_per_pass,
        dry_run=dry_run,
    )

    atom_cutoff = cutoff_now - timedelta(days=deprecated_atom_days)
    stats.deprecated_atoms_deleted = _gc_deprecated_atoms(
        memory,
        cutoff=atom_cutoff,
        limit=max_rows_per_pass,
        dry_run=dry_run,
    )

    if include_orphan_raw:
        raw_cutoff = cutoff_now - timedelta(days=orphan_raw_days)
        stats.orphan_raw_events_deleted = _gc_orphan_raw_events(
            memory,
            cutoff=raw_cutoff,
            limit=max_rows_per_pass,
            dry_run=dry_run,
        )

    journal_cutoff = cutoff_now - timedelta(days=journal_pipeline_days)
    stats.journal_rows_deleted = _gc_pipeline_journal(
        memory,
        cutoff=journal_cutoff,
        limit=max_rows_per_pass,
        dry_run=dry_run,
    )

    stats.finished_at = datetime.now(UTC)
    return stats


# ---------------------------------------------------------------------------
# Sub-pass helpers
# ---------------------------------------------------------------------------


def _gc_rejected_candidates(
    memory: Memory,
    *,
    cutoff: datetime,
    limit: int,
    dry_run: bool,
) -> int:
    """Delete candidates with status='rejected' and decided_at < cutoff."""
    deleted = 0
    rejected = memory.list_candidates(status="rejected", limit=limit)
    for cand in rejected:
        if not cand.decided_at or cand.decided_at >= cutoff:
            continue
        if not dry_run:
            _delete_candidate(memory, cand.id)
        deleted += 1
    return deleted


def _gc_deprecated_atoms(
    memory: Memory,
    *,
    cutoff: datetime,
    limit: int,
    dry_run: bool,
) -> int:
    deleted = 0
    atoms = memory.list_atoms(include_deprecated=True, limit=limit)
    for atom in atoms:
        if not atom.deprecated_at or atom.deprecated_at >= cutoff:
            continue
        if not dry_run:
            _delete_atom(memory, atom.id)
        deleted += 1
    return deleted


def _gc_orphan_raw_events(
    memory: Memory,
    *,
    cutoff: datetime,
    limit: int,
    dry_run: bool,
) -> int:
    """Delete unreferenced raw rows older than ``cutoff``.

    Id-only SQL — never hydrate ``content`` / ``payload``. The previous
    ``list_raw(limit=10**9)`` path loaded every blob into Python and
    OOM'd on multi-GB stores before VACUUM could run.
    """
    conn, ns = _sqlite_conn(memory)
    referenced = _referenced_raw_ids(conn, ns)
    cutoff_iso = cutoff.isoformat()
    victims: list[str] = []
    for row in conn.execute(
        f"SELECT id, timestamp FROM {ns}_raw_events WHERE timestamp < ?",
        (cutoff_iso,),
    ):
        raw_id = row["id"]
        if raw_id in referenced:
            continue
        victims.append(raw_id)
        if len(victims) >= limit:
            break

    if not dry_run:
        for raw_id in victims:
            _delete_raw_event(memory, raw_id)
    return len(victims)


def _referenced_raw_ids(conn: Any, ns: str) -> set[str]:
    """Collect raw ids cited by atoms / candidates. Columns only, no blobs."""
    referenced: set[str] = set()
    for row in conn.execute(f"SELECT quote_event_id, raw_event_ids FROM {ns}_atoms"):
        quote_id = row["quote_event_id"]
        if quote_id:
            referenced.add(quote_id)
        referenced.update(_json_id_list(row["raw_event_ids"]))
    for row in conn.execute(f"SELECT raw_event_ids FROM {ns}_candidates"):
        referenced.update(_json_id_list(row["raw_event_ids"]))
    return referenced


def _json_id_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str) and item]


def _gc_pipeline_journal(
    memory: Memory,
    *,
    cutoff: datetime,
    limit: int,
    dry_run: bool,
) -> int:
    """Expire observability journal rows. Does not append journal."""
    return memory.delete_journal(
        actions=PIPELINE_JOURNAL_ACTIONS,
        before=cutoff,
        limit=limit,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Backend pokes (SQLite-only for M5; D46-C postpones PG)
# ---------------------------------------------------------------------------


def _sqlite_backend(memory: Memory) -> Any | None:
    from octop_memory.storage.backends.sqlite import SqliteMemoryBackend

    backend = getattr(memory, "_backend", None)
    if isinstance(backend, SqliteMemoryBackend):
        return backend
    return None


def _sqlite_conn(memory: Memory) -> tuple[Any, str]:
    """Return the SQLite connection and table prefix, or refuse before touching SQL.

    Duck-typing on ``_conn`` / ``_ns`` is not enough: ``PostgresMemoryBackend``
    exposes both, so it used to pass this guard and then run SQLite statements
    (``{ns}_atoms``, ``?`` placeholders) against Postgres. That raised
    ``UndefinedTable`` mid-transaction and left the shared psycopg connection
    aborted, so every later memory write failed with ``InFailedSqlTransaction``.
    Refuse on type instead, before any statement reaches the connection.
    """
    backend = _sqlite_backend(memory)
    if backend is None:
        raise RuntimeError(
            "GC requires SQLite backend (D46-C; PG support deferred to M6); "
            f"got {type(getattr(memory, '_backend', None)).__name__}"
        )
    conn = getattr(backend, "_conn", None)
    ns = getattr(backend, "_ns", None)
    if conn is None or ns is None:
        raise RuntimeError("GC requires SQLite backend (D46-C; PG support deferred to M6)")
    return conn, ns


def _delete_candidate(memory: Memory, candidate_id: str) -> None:
    """Remove a candidate row by id. SQLite-only; PG impl in M6."""
    conn, ns = _sqlite_conn(memory)
    conn.execute(f"DELETE FROM {ns}_candidates WHERE id = ?", (candidate_id,))
    conn.commit()


def _delete_atom(memory: Memory, atom_id: str) -> None:
    conn, ns = _sqlite_conn(memory)
    # Triggers on the atoms table keep the atoms_fts shadow in sync,
    # so DELETE FROM atoms is enough — no manual FTS cleanup needed.
    conn.execute(f"DELETE FROM {ns}_atoms WHERE id = ?", (atom_id,))
    conn.commit()


def _delete_raw_event(memory: Memory, raw_id: str) -> None:
    conn, ns = _sqlite_conn(memory)
    # Same: triggers keep the raw FTS in sync.
    conn.execute(f"DELETE FROM {ns}_raw_events WHERE id = ?", (raw_id,))
    conn.commit()


__all__ = [
    "DEFAULT_DEPRECATED_ATOM_DAYS",
    "DEFAULT_JOURNAL_PIPELINE_DAYS",
    "DEFAULT_MAX_ROWS_PER_PASS",
    "DEFAULT_ORPHAN_RAW_DAYS",
    "DEFAULT_REJECTED_CANDIDATE_DAYS",
    "PIPELINE_JOURNAL_ACTIONS",
    "GcStats",
    "run_gc",
]
