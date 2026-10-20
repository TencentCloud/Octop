"""Storage-level space reclamation (RISK-026 vacuum plan, ADR-025).

Deleting rows (lifecycle GC, checkpoint pruning, journal retention) only
marks the space they occupied as reusable — it never shrinks the on-disk
footprint on its own, on either backend. This module is the second half
of that story: giving the reclaimed space back.

The two backends need genuinely different treatment, not a shared code
path with an `if backend == "postgres"` branch bolted on:

* **SQLite** has no engine-level background reclaim process.
  :func:`nudge_vacuum` runs ``PRAGMA incremental_vacuum`` in small,
  bounded batches (cheap, safe with live traffic once
  ``auto_vacuum=INCREMENTAL`` is on — new files start that way, see
  ADR-027; hosts schedule this via :func:`run_idle_maintenance`).
  :func:`compact_vacuum` runs a full ``VACUUM`` (rebuilds the whole
  file, exclusive lock — only during a confirmed idle window; still
  manual, not on the idle tick).

* **PostgreSQL** already runs `autovacuum` in the background by default,
  reclaiming dead-tuple space for reuse without blocking readers or
  writers — the SQLite problem this module mostly exists to solve
  doesn't exist on Postgres. :func:`nudge_vacuum` here just runs a plain
  (non-blocking) ``VACUUM`` on the specific high-churn tables
  (``journal`` plus LangGraph's ``checkpoints``/``checkpoint_blobs``/
  ``checkpoint_writes``, none of which have a ``namespace`` column — see
  RISK-026) as an on-demand nudge on top of autovacuum.
  :func:`compact_vacuum` runs ``VACUUM FULL`` per table, which — unlike
  SQLite's ``VACUUM`` — takes an ``ACCESS EXCLUSIVE`` lock that blocks
  *reads* too, and does so on tables shared by every namespace on that
  Postgres instance. Callers should treat it as a manual, ops-invoked
  operation, not something to schedule blindly (see ADR-025).

Three entry points, split by *what they cost* rather than by backend
(the CLI mirrors this as ``octop-memory db check`` / ``vacuum`` / ``compact``):

* :func:`check_storage` — read-only; never mutates, always safe.
* :func:`nudge_vacuum` — cheap and bounded; safe with live traffic.
* :func:`compact_vacuum` — heavy; holds an exclusive lock.

Both backends' :func:`nudge_vacuum` are safe to call from a host's idle
timer (see ``octop-harness``'s ``MemoryMiddleware``). :func:`compact_vacuum`
is not — it must only run when the caller has confirmed there's no
concurrent traffic (for Postgres: no other namespace/host either, since
the affected tables are shared — see RISK-026's Postgres section).

The mutating pair still take a ``dry_run`` flag, but it is *not* the
user-facing inspection surface — :func:`check_storage` is (ADR-025).
``dry_run`` exists so those previews stay exact (they predict the real
outcome rather than reporting a bare zero), and so ``check_storage``
can reuse them; the CLI deliberately exposes no ``--dry-run`` option.
"""

from __future__ import annotations

import logging
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from octop_memory.storage.backends.sqlite import locked_sqlite_operation

if TYPE_CHECKING:
    from octop_memory.core import Memory
    from octop_memory.storage.backends.postgres import PostgresMemoryBackend
    from octop_memory.storage.backends.sqlite import SqliteMemoryBackend

_LOG = logging.getLogger(__name__)

DEFAULT_INCREMENTAL_VACUUM_PAGES = 300
"""~1.2MB reclaimed per call at the default 4KB SQLite page size — small
enough that a single nudge_vacuum() stays fast even under lock contention."""

DELETE_INCREMENTAL_VACUUM_PAGES = 2000
"""~8MB at the default 4KB page size. One pass after a conversation delete,
then return to the caller. Larger holes drain on the hourly maintenance tick."""

MAINTENANCE_INCREMENTAL_VACUUM_PAGES = 5000
"""~20MB at the default 4KB page size. Hourly tick budget when the freelist
is larger than :data:`DEFAULT_INCREMENTAL_VACUUM_PAGES`. ``nudge_vacuum``
already stops at the freelist, so a small hole still finishes in one tick."""

_POSTGRES_JOURNAL_TABLE = "octop_memory.journal"
_POSTGRES_CHECKPOINT_TABLES = (
    "public.checkpoints",
    "public.checkpoint_blobs",
    "public.checkpoint_writes",
)
"""LangGraph's own tables (langgraph-checkpoint-postgres), not part of
octop-memory's schema — created by PostgresSaver.setup() in whatever
schema the connection's search_path resolves to (default: public). No
namespace column; shared across every namespace on the instance."""

_CHECKPOINT_AUTOVACUUM_STORAGE_PARAMS = "autovacuum_vacuum_scale_factor = 0.05, autovacuum_vacuum_cost_delay = 2"
"""Default PG autovacuum_vacuum_scale_factor (0.2) waits for dead tuples
to reach 20% of table size before triggering — too conservative for
journal/checkpoint tables under steady churn. 0.05 is a starting point,
not a measured optimum; cheap to retune later (ALTER TABLE ... SET is
non-blocking and takes effect immediately)."""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class TableVacuumResult:
    """Per-table outcome for a Postgres vacuum pass."""

    table: str
    action: str
    skipped_reason: str | None = None
    """Set (instead of running the action) when the table doesn't exist —
    e.g. the LangGraph checkpoint extras were never installed."""


@dataclass
class VacuumStats:
    """Result of one :func:`nudge_vacuum` call — cheap, safe with live traffic."""

    backend: str  # "sqlite" | "postgres"
    dry_run: bool = False
    # SQLite fields
    auto_vacuum_enabled: bool | None = None
    freelist_pages_before: int | None = None
    pages_reclaimed: int | None = None
    skipped_reason: str | None = None
    """Set when the pass declined to do anything for a reason the caller
    should be able to tell apart from "nothing to reclaim" — currently only
    "a transaction was in flight on the shared connection"."""
    # Postgres fields
    tables: list[TableVacuumResult] = field(default_factory=list)


@dataclass
class CompactStats:
    """Result of one :func:`compact_vacuum` call — heavy, needs a real idle window."""

    backend: str
    dry_run: bool = False
    # SQLite fields
    file_size_before: int | None = None
    file_size_after: int | None = None
    auto_vacuum_was_enabled: bool | None = None
    # Postgres fields
    tables: list[TableVacuumResult] = field(default_factory=list)


@dataclass
class TableCheck:
    """Per-table read-only diagnostics for a Postgres store."""

    table: str
    exists: bool
    live_tuples: int | None = None
    dead_tuples: int | None = None
    """Postgres' equivalent of SQLite's freelist: rows superseded by
    UPDATE/DELETE whose space autovacuum has not reclaimed yet."""
    last_vacuum: str | None = None
    last_autovacuum: str | None = None


@dataclass
class StorageCheck:
    """Read-only storage health report — the result of :func:`check_storage`.

    Never mutates anything, so it is always safe to run (that is the whole
    reason it exists as its own entry point rather than a ``dry_run`` flag
    on the mutating calls — see ADR-025).
    """

    backend: str
    # SQLite fields
    auto_vacuum_enabled: bool | None = None
    page_size: int | None = None
    total_pages: int | None = None
    freelist_pages: int | None = None
    reclaimable_bytes: int | None = None
    """``freelist_pages * page_size`` — space the file holds but doesn't use."""
    would_reclaim_pages: int | None = None
    """What a single :func:`nudge_vacuum` call would actually reclaim right
    now, i.e. ``min(default page budget, freelist_pages)`` — a precise
    prediction, not just the raw freelist total."""
    file_size: int | None = None
    wal_size: int | None = None
    # Postgres fields
    tables: list[TableCheck] = field(default_factory=list)
    # Both
    recommendations: list[str] = field(default_factory=list)
    """Actionable next steps, e.g. "run `octop-memory db compact --yes` once"."""


# ---------------------------------------------------------------------------
# Public entry points — backend dispatch lives here, not in callers
# ---------------------------------------------------------------------------


def nudge_vacuum(
    memory: Memory,
    *,
    pages: int = DEFAULT_INCREMENTAL_VACUUM_PAGES,
    dry_run: bool = False,
) -> VacuumStats:
    """Cheap, bounded space reclaim — safe to call with live traffic.

    SQLite: ``PRAGMA incremental_vacuum``, reclaiming at most ``pages``
    pages per call. New files open with ``auto_vacuum=INCREMENTAL``
    already on (ADR-027). Legacy NONE databases still reclaim nothing
    until :func:`compact_vacuum` has run once — that state is reported
    as ``auto_vacuum_enabled=False`` rather than an unexplained
    ``pages_reclaimed=0``, so callers can tell "nothing to reclaim"
    apart from "can't reclaim yet". Postgres: plain ``VACUUM`` on
    ``journal`` and the LangGraph checkpoint tables — never blocks
    readers or writers, just nudges autovacuum's job forward.

    With ``dry_run=True`` nothing is touched and ``pages_reclaimed``
    carries an *exact* prediction of what a real call would reclaim
    (``min(pages, freelist)``), not a placeholder zero. Prefer
    :func:`check_storage` for user-facing inspection — it reports this
    plus file/WAL sizes and actionable recommendations.
    """
    from octop_memory.storage.backends.sqlite import SqliteMemoryBackend

    backend = memory._backend
    if isinstance(backend, SqliteMemoryBackend):
        return _sqlite_nudge_vacuum(backend, pages=pages, dry_run=dry_run)

    try:
        from octop_memory.storage.backends.postgres import PostgresMemoryBackend
    except ImportError:
        # psycopg isn't installed, so `backend` can't possibly be a real
        # PostgresMemoryBackend either (it can't construct without
        # psycopg) — fall through to the "unsupported" error below
        # instead of letting this import blow up on an unrelated backend.
        pass
    else:
        if isinstance(backend, PostgresMemoryBackend):
            return _postgres_nudge_vacuum(backend, dry_run=dry_run)

    raise RuntimeError(f"nudge_vacuum: unsupported backend {type(backend).__name__!r}")


def compact_vacuum(memory: Memory, *, dry_run: bool = False) -> CompactStats:
    """Heavy, exclusive-lock space reclaim — only run during a confirmed idle window.

    SQLite: one full ``VACUUM`` (bootstraps ``auto_vacuum=INCREMENTAL`` on
    first call if it isn't already on — that pragma can only take effect
    via a full rebuild, so this doubles as the one-time migration and the
    periodic deep-compaction pass). Postgres: ``VACUUM FULL`` per table —
    takes an ``ACCESS EXCLUSIVE`` lock that blocks reads too, on tables
    shared by every namespace on the instance. See module docstring and
    ADR-025 before wiring this into any automatic scheduler.

    ``dry_run=True`` reports the *current* size but cannot predict the
    post-compaction one: that depends on fragmentation, which there is no
    cheap way to model. This is a real limitation of this preview, not an
    oversight — :func:`check_storage` is the better inspection entry
    point, since ``reclaimable_bytes`` there at least quantifies the
    known-wasted space.
    """
    from octop_memory.storage.backends.sqlite import SqliteMemoryBackend

    backend = memory._backend
    if isinstance(backend, SqliteMemoryBackend):
        return _sqlite_compact_vacuum(backend, dry_run=dry_run)

    try:
        from octop_memory.storage.backends.postgres import PostgresMemoryBackend
    except ImportError:
        pass
    else:
        if isinstance(backend, PostgresMemoryBackend):
            return _postgres_compact_vacuum(backend, dry_run=dry_run)

    raise RuntimeError(f"compact_vacuum: unsupported backend {type(backend).__name__!r}")


def check_storage(memory: Memory) -> StorageCheck:
    """Read-only storage health report — never mutates, always safe to run.

    Answers both "how much space is being wasted right now" and "what
    would each maintenance command actually do", so callers never have to
    invoke a mutating command in a fake mode just to look. Surfaced as
    ``octop-memory db check``.
    """
    from octop_memory.storage.backends.sqlite import SqliteMemoryBackend

    backend = memory._backend
    if isinstance(backend, SqliteMemoryBackend):
        return _sqlite_check(backend)

    try:
        from octop_memory.storage.backends.postgres import PostgresMemoryBackend
    except ImportError:
        pass
    else:
        if isinstance(backend, PostgresMemoryBackend):
            return _postgres_check(backend)

    raise RuntimeError(f"check_storage: unsupported backend {type(backend).__name__!r}")


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------


@locked_sqlite_operation
def _sqlite_nudge_vacuum(backend: SqliteMemoryBackend, *, pages: int, dry_run: bool) -> VacuumStats:
    conn = backend._conn
    auto_vacuum_mode = conn.execute("PRAGMA auto_vacuum").fetchone()[0]
    enabled = auto_vacuum_mode == 2  # 0=NONE, 1=FULL, 2=INCREMENTAL
    freelist_before = conn.execute("PRAGMA freelist_count").fetchone()[0]

    if not dry_run and conn.in_transaction:
        # This backend already has an open write transaction owned by this
        # thread (``SqliteMemoryBackend.transaction()``). Reclaiming
        # now would enlist vacuum in *that* transaction: a later rollback
        # undoes the reclaim, so we would report pages we did not free.
        # Skip — the idle timer retries on the next tick. Other threads
        # wait for the backend's transaction lock before reaching here.
        return VacuumStats(
            backend="sqlite",
            dry_run=False,
            auto_vacuum_enabled=enabled,
            freelist_pages_before=freelist_before,
            pages_reclaimed=0,
            skipped_reason="a transaction is in progress on this connection",
        )

    if not enabled:
        # Not an error: incremental_vacuum is a silent no-op until a
        # compact_vacuum() has bootstrapped auto_vacuum=INCREMENTAL.
        # Surfacing that explicitly (rather than reporting
        # pages_reclaimed=0 with no explanation) lets callers tell
        # "nothing to reclaim" apart from "can't reclaim yet".
        return VacuumStats(
            backend="sqlite",
            dry_run=dry_run,
            auto_vacuum_enabled=False,
            freelist_pages_before=freelist_before,
            pages_reclaimed=0,
        )

    if dry_run:
        # Predict the real outcome rather than reporting a bare 0: a real
        # call reclaims one page per loop iteration until either the page
        # budget or the freelist runs out, so min() is exact, not an
        # estimate. check_storage() surfaces this as would_reclaim_pages.
        return VacuumStats(
            backend="sqlite",
            dry_run=True,
            auto_vacuum_enabled=True,
            freelist_pages_before=freelist_before,
            pages_reclaimed=min(pages, freelist_before),
        )

    # Why a Python-side loop instead of one `incremental_vacuum(pages)` call.
    #
    # Measured on CPython 3.11 / SQLite 3.44 (fresh identical DBs per run):
    #
    #   conn.execute("PRAGMA incremental_vacuum(N)")   -> 1 page, any N
    #     ...same with .fetchall() / iterating the cursor (it yields no rows;
    #     cursor.description is None, so the module treats it as a statement
    #     that returns nothing and steps it exactly once)
    #   conn.executescript("PRAGMA incremental_vacuum(N);") -> min(N, freelist)
    #
    # So `executescript` *would* honour the page budget in a single call, and
    # is marginally faster (1.6ms vs 2.2ms for 300 pages). We deliberately do
    # NOT use it: executescript issues an implicit COMMIT first (measured —
    # an uncommitted INSERT on the same connection became visible to other
    # connections after the call). This function is designed to be called
    # from a host's background idle timer while the agent may be mid-write,
    # and SqliteMemoryBackend shares one `check_same_thread=False` connection
    # whose `transaction()` context manager exists precisely to keep
    # multi-table writes atomic (see RISK-013). Committing someone else's
    # half-finished transaction to save 0.6ms is a bad trade; the loop leaves
    # `in_transaction` untouched (also measured).
    #
    # Cost of the loop is fine: ~2.2ms for the 300-page default.
    remaining = freelist_before
    reclaimed = 0
    for _ in range(pages):
        if remaining <= 0:
            break
        conn.execute("PRAGMA incremental_vacuum(1)")
        remaining -= 1
        reclaimed += 1
    # No conn.commit() here on purpose. We only reach this point when the
    # connection had no transaction in flight (guarded above), so the pragma
    # runs in autocommit and each reclaimed page is already durable —
    # verified by reopening the file from a second connection. Calling
    # commit() would be worse than redundant: if the guard above ever
    # regresses, it would silently commit somebody else's open transaction.
    # incremental_vacuum's effect lands in the WAL first (journal_mode=WAL
    # is the default — see sqlite.py __init__), not the main file: verified
    # empirically that without a checkpoint, the -wal file grows by roughly
    # what the main file *would* have shrunk by, so skipping this would
    # make nudge_vacuum a net loss (bigger WAL, same-size main file) rather
    # than a reclaim. PASSIVE never blocks readers/writers — unlike TRUNCATE,
    # it just folds WAL frames into the main file opportunistically, so this
    # keeps the "safe with live traffic" contract intact. It doesn't shrink
    # the -wal file itself (that needs TRUNCATE — compact_vacuum and idle
    # maybe_truncate_wal, ADR-027 P3).
    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    return VacuumStats(
        backend="sqlite",
        dry_run=False,
        auto_vacuum_enabled=True,
        freelist_pages_before=freelist_before,
        pages_reclaimed=reclaimed,
    )


def _sqlite_store_bytes(db_path: Path) -> int:
    """Main database plus WAL and shm, matching one Postgres database size."""
    total = 0
    for candidate in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
        if candidate.is_file():
            total += candidate.stat().st_size
    return total


@locked_sqlite_operation
def _sqlite_compact_vacuum(backend: SqliteMemoryBackend, *, dry_run: bool) -> CompactStats:
    conn = backend._conn
    db_path = backend._db_path
    size_before = _sqlite_store_bytes(db_path)
    auto_vacuum_mode = conn.execute("PRAGMA auto_vacuum").fetchone()[0]
    was_enabled = auto_vacuum_mode == 2

    if dry_run:
        return CompactStats(
            backend="sqlite",
            dry_run=True,
            file_size_before=size_before,
            file_size_after=size_before,
            auto_vacuum_was_enabled=was_enabled,
        )

    if not was_enabled:
        # auto_vacuum can only be *changed* by a full VACUUM rebuild, and
        # the pragma must be set before that VACUUM runs — this is the
        # one-time bootstrap, folded into the same call so there's no
        # separate "migrate" step callers have to remember to run first.
        conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
    _LOG.info("compact_vacuum start path=%s size_before=%s", db_path, size_before)
    conn.execute("VACUUM")
    conn.commit()
    # VACUUM rebuilds the file, but in journal_mode=WAL (the default here —
    # see sqlite.py __init__) the smaller size isn't visible on disk until
    # a checkpoint runs: verified empirically — os.stat() kept reporting
    # the pre-VACUUM size until this ran, even after VACUUM + commit().
    # Without this, compact_vacuum() would report (and callers would
    # believe) that nothing was reclaimed.
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    size_after = _sqlite_store_bytes(db_path)
    _LOG.info(
        "compact_vacuum done path=%s size_before=%s size_after=%s",
        db_path,
        size_before,
        size_after,
    )
    return CompactStats(
        backend="sqlite",
        dry_run=False,
        file_size_before=size_before,
        file_size_after=size_after,
        auto_vacuum_was_enabled=True,
    )


@locked_sqlite_operation
def _sqlite_check(backend: SqliteMemoryBackend) -> StorageCheck:
    conn = backend._conn
    db_path = backend._db_path
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    total_pages = conn.execute("PRAGMA page_count").fetchone()[0]
    freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
    enabled = conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2

    wal_path = db_path.with_name(db_path.name + "-wal")
    check = StorageCheck(
        backend="sqlite",
        auto_vacuum_enabled=enabled,
        page_size=page_size,
        total_pages=total_pages,
        freelist_pages=freelist,
        reclaimable_bytes=freelist * page_size,
        # A nudge can only reclaim once auto_vacuum is INCREMENTAL; before
        # that the honest answer is 0, with the recommendation below saying
        # how to unlock it.
        would_reclaim_pages=min(DEFAULT_INCREMENTAL_VACUUM_PAGES, freelist) if enabled else 0,
        file_size=db_path.stat().st_size if db_path.exists() else 0,
        wal_size=wal_path.stat().st_size if wal_path.exists() else 0,
    )

    if not enabled:
        check.recommendations.append(
            "auto_vacuum is NONE — run `octop-memory db compact --yes` once (during an idle window) "
            "to enable INCREMENTAL mode; `octop-memory db vacuum` cannot reclaim anything until then."
        )
    elif freelist > DEFAULT_INCREMENTAL_VACUUM_PAGES:
        check.recommendations.append(
            f"{freelist} free pages ({freelist * page_size} bytes) pending — more than one "
            f"`octop-memory db vacuum` can clear at the default budget of "
            f"{DEFAULT_INCREMENTAL_VACUUM_PAGES}; run it repeatedly, or "
            "`octop-memory db compact --yes` once during an idle window."
        )
    elif freelist > 0:
        check.recommendations.append(f"{freelist} free pages pending — one `octop-memory db vacuum` clears them.")
    return check


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------


def _postgres_nudge_vacuum(backend: PostgresMemoryBackend, *, dry_run: bool) -> VacuumStats:
    tables = _postgres_vacuum_tables(backend._dsn, _postgres_target_tables(), full=False, dry_run=dry_run)
    return VacuumStats(backend="postgres", dry_run=dry_run, tables=tables)


def _postgres_database_bytes(dsn: str) -> int:
    from psycopg.rows import tuple_row

    from octop_memory.storage.backends.postgres_pool import maintenance_connection

    with maintenance_connection(dsn) as conn, conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT pg_database_size(current_database())")
        row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _postgres_compact_vacuum(backend: PostgresMemoryBackend, *, dry_run: bool) -> CompactStats:
    size_before = _postgres_database_bytes(backend._dsn)
    tables = _postgres_vacuum_tables(backend._dsn, _postgres_target_tables(), full=True, dry_run=dry_run)
    size_after = size_before if dry_run else _postgres_database_bytes(backend._dsn)
    return CompactStats(
        backend="postgres",
        dry_run=dry_run,
        file_size_before=size_before,
        file_size_after=size_after,
        tables=tables,
    )


def _postgres_check(backend: PostgresMemoryBackend) -> StorageCheck:
    """Read dead-tuple counts + last-vacuum times straight from pg_stat_user_tables.

    Dead tuples are Postgres' analogue of SQLite's freelist: space held by
    rows that UPDATE/DELETE superseded and autovacuum hasn't reclaimed
    yet. Unlike SQLite there is no "is the feature even on" question —
    autovacuum ships enabled — so the recommendations here are about
    whether it is keeping *up*, not whether it exists.
    """
    from psycopg.rows import tuple_row

    from octop_memory.storage.backends.postgres_pool import maintenance_connection

    check = StorageCheck(backend="postgres")
    with maintenance_connection(backend._dsn) as conn, conn.cursor(row_factory=tuple_row) as cur:
        for qualified in _postgres_target_tables():
            schema, _, table = qualified.partition(".")
            cur.execute(
                """SELECT n_live_tup, n_dead_tup, last_vacuum, last_autovacuum
                   FROM pg_stat_user_tables WHERE schemaname = %s AND relname = %s""",
                (schema, table),
            )
            row = cur.fetchone()
            if row is None:
                check.tables.append(TableCheck(table=qualified, exists=False))
                continue
            live, dead, last_vacuum, last_autovacuum = row[0], row[1], row[2], row[3]
            check.tables.append(
                TableCheck(
                    table=qualified,
                    exists=True,
                    live_tuples=live,
                    dead_tuples=dead,
                    last_vacuum=last_vacuum.isoformat() if last_vacuum else None,
                    last_autovacuum=last_autovacuum.isoformat() if last_autovacuum else None,
                )
            )

    bloated = [t for t in check.tables if t.exists and (t.dead_tuples or 0) > (t.live_tuples or 0)]
    if bloated:
        names = ", ".join(t.table for t in bloated)
        check.recommendations.append(
            f"dead tuples exceed live rows on: {names} — autovacuum may be falling behind; "
            "`octop-memory db vacuum` nudges it without blocking anyone."
        )
    if not any(t.exists for t in check.tables):
        check.recommendations.append("none of the target tables exist yet — nothing to maintain on this database.")
    return check


def _postgres_target_tables() -> tuple[str, ...]:
    return (_POSTGRES_JOURNAL_TABLE, *_POSTGRES_CHECKPOINT_TABLES)


def _postgres_vacuum_tables(dsn: str, tables: tuple[str, ...], *, full: bool, dry_run: bool) -> list[TableVacuumResult]:
    """Run (or preview) VACUUM / VACUUM FULL on each table.

    Uses its own short-lived connection rather than the backend's main
    one — VACUUM cannot run inside a transaction block, and this avoids
    touching the autocommit/transaction state of a connection the rest
    of ``PostgresMemoryBackend`` is concurrently using (same rationale as
    ``core.py`` giving the checkpointer its own connection).
    """
    from psycopg.rows import tuple_row

    from octop_memory.storage.backends.postgres_pool import maintenance_connection

    results: list[TableVacuumResult] = []
    with maintenance_connection(dsn) as conn, conn.cursor(row_factory=tuple_row) as cur:
        for table in tables:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
            row = cur.fetchone()
            exists = bool(row[0]) if row else False
            if not exists:
                results.append(TableVacuumResult(table=table, action="skip", skipped_reason="table does not exist"))
                continue
            verb = "VACUUM FULL" if full else "VACUUM"
            if dry_run:
                results.append(TableVacuumResult(table=table, action=f"would run {verb}"))
                continue
            # Table names are drawn only from the fixed allowlists above,
            # never from caller input — VACUUM/identifiers can't be
            # parameterized via %s, same constraint sqlite.py already
            # works around with f-string-interpolated {ns}_journal etc.
            cur.execute(f"{verb} {table}")
            results.append(TableVacuumResult(table=table, action=verb))
    return results


def tune_checkpoint_autovacuum(dsn: str, *, connection: Any = None) -> None:
    """Loosen autovacuum thresholds on LangGraph's checkpoint tables.

    Called once after ``PostgresSaver.setup()`` creates them
    (``core.py::_create_checkpointer``) — they're third-party-managed
    tables outside ``postgres.py``'s own DDL, so there's no ``_init_schema``
    hook to piggyback this onto. Silently skips tables that don't exist
    yet (setup() may have been a no-op, or a version mismatch changed
    the table set). Idempotent: re-running with the same values is a
    cheap no-op ALTER, safe to call on every checkpointer construction.
    """
    from psycopg.rows import tuple_row

    from octop_memory.storage.backends.postgres_pool import maintenance_connection

    connection_scope = nullcontext(connection) if connection is not None else maintenance_connection(dsn)
    with connection_scope as conn, conn.cursor(row_factory=tuple_row) as cur:
        for table in _POSTGRES_CHECKPOINT_TABLES:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
            row = cur.fetchone()
            if not (row and row[0]):
                continue
            cur.execute(f"ALTER TABLE {table} SET ({_CHECKPOINT_AUTOVACUUM_STORAGE_PARAMS})")


__all__ = [
    "DEFAULT_INCREMENTAL_VACUUM_PAGES",
    "DELETE_INCREMENTAL_VACUUM_PAGES",
    "MAINTENANCE_INCREMENTAL_VACUUM_PAGES",
    "CompactStats",
    "StorageCheck",
    "TableCheck",
    "TableVacuumResult",
    "VacuumStats",
    "check_storage",
    "compact_vacuum",
    "nudge_vacuum",
    "tune_checkpoint_autovacuum",
]
