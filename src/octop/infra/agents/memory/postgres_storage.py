"""Bounded, namespace-scoped PostgreSQL cleanup; never vacuum shared tables.

The host supplies the live backend's namespace, pauses only its expert, and
keeps a durable JSONL copy of the exact locked rows before deleting them.
Checkpoints, raw evidence, active memories and decision journals are untouched.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from octop.i18n import tr

LIMIT_PER_TABLE = 500
CANDIDATE_DAYS = 30
JOURNAL_DAYS = 14
# Consolidation records are decisions too; keep them along with promote/reject.
PIPELINE_ACTIONS = (
    "extract_run",
    "gc_rejected_candidate",
    "gc_deprecated_atom",
    "gc_orphan_raw_event",
    "page_regen",
    "page_regen_failed",
)
TABLES = (
    "raw_events",
    "candidates",
    "atoms",
    "entities",
    "aliases",
    "entity_pages",
    "memory_nodes",
    "thread_active_entities",
    "journal",
    "episodes",
    "digests",
)


def _predicates(namespace: str, now: datetime) -> dict[str, tuple[str, tuple[Any, ...]]]:
    return {
        "candidates": (
            "t.namespace = %s AND t.status = 'rejected' AND t.decided_at < %s "
            "AND NOT EXISTS (SELECT 1 FROM octop_memory.atoms a "
            "WHERE a.namespace = t.namespace AND a.candidate_id = t.id)",
            (namespace, now - timedelta(days=CANDIDATE_DAYS)),
        ),
        "journal": (
            "t.namespace = %s AND t.action = ANY(%s) AND t.timestamp < %s",
            (namespace, list(PIPELINE_ACTIONS), now - timedelta(days=JOURNAL_DAYS)),
        ),
    }


def _connect(backend: Any) -> Any:
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(backend._dsn, connect_timeout=5, row_factory=dict_row)


def inspect_postgres_storage(backend: Any, *, blocked_reason: str | None = None) -> dict[str, Any]:
    """Exact per-namespace row counts; row sizes are not physical free space."""
    from psycopg import sql

    namespace = backend._ns
    now = datetime.now(UTC)
    tables = []
    eligible: dict[str, int] = {}
    with _connect(backend) as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '15s'")
        cur.execute("SET LOCAL lock_timeout = '1s'")
        for table in TABLES:
            cur.execute(
                sql.SQL(
                    "SELECT count(*) AS rows, COALESCE(sum(pg_column_size(t)), 0) AS row_bytes "
                    "FROM octop_memory.{} t WHERE namespace = %s"
                ).format(sql.Identifier(table)),
                (namespace,),
            )
            row = cur.fetchone()
            tables.append(
                {"table": table, "rows": int(row["rows"]), "row_bytes": int(row["row_bytes"])}
            )
        for table, (predicate, params) in _predicates(namespace, now).items():
            cur.execute(
                sql.SQL(
                    "SELECT count(*) AS rows FROM (SELECT t.id FROM octop_memory.{} t WHERE "
                    + predicate
                    + " LIMIT %s) eligible"
                ).format(sql.Identifier(table)),
                (*params, LIMIT_PER_TABLE),
            )
            eligible[table] = int(cur.fetchone()["rows"])
    return {
        "backend": "postgres",
        "scope": "agent",
        "checked_at": time.time(),
        "maintenance_supported": blocked_reason is None,
        "blocked_reason": blocked_reason,
        "namespace": namespace,
        "namespace_tables": tables,
        "cleanup_preview": {
            **eligible,
            "total": sum(eligible.values()),
            "limit_per_table": LIMIT_PER_TABLE,
            "candidate_days": CANDIDATE_DAYS,
            "journal_days": JOURNAL_DAYS,
        },
    }


def maintain_postgres_storage(
    backend: Any,
    *,
    backup: Path,
    progress: Callable[[dict[str, Any]], None],
    locale: str = "en",
) -> dict[str, Any]:
    """Back up exact victims, then delete atomically with namespace+id predicates.

    SKIP LOCKED avoids waiting on an in-flight update. One bounded transaction
    holds only target-row locks; ordinary reads/writes in other namespaces
    proceed. A per-namespace advisory lock folds concurrent manual jobs across
    hosts. No DDL, table locks, checkpoint pruning or VACUUM is issued.
    """
    from psycopg import sql

    namespace = backend._ns
    now = datetime.now(UTC)
    victims: dict[str, list[dict[str, Any]]] = {}
    progress({"phase": "inspecting"})
    with _connect(backend) as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '15s'")
        cur.execute("SET LOCAL lock_timeout = '1s'")
        cur.execute(
            "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0)) AS acquired",
            (f"octop:memory-maintenance:{namespace}",),
        )
        if not cur.fetchone()["acquired"]:
            raise ValueError(tr("memory_storage.namespace_busy", locale))
        for table, (predicate, params) in _predicates(namespace, now).items():
            # Generated FTS columns are derived, and must not be restored as data.
            cur.execute(
                sql.SQL(
                    "SELECT t.id, (to_jsonb(t) - 'fts_tsv') AS data FROM octop_memory.{} t WHERE "
                    + predicate
                    + " ORDER BY t.id LIMIT %s FOR UPDATE OF t SKIP LOCKED"
                ).format(sql.Identifier(table)),
                (*params, LIMIT_PER_TABLE),
            )
            victims[table] = list(cur.fetchall())
        total = sum(len(rows) for rows in victims.values())
        if total:
            progress({"phase": "backing_up", "scanned": 0, "total": total})
            backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(
                            {
                                "format": "octop-postgres-namespace-cleanup-v1",
                                "namespace": namespace,
                                "created_at": now.isoformat(),
                                "rows": total,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    for table, rows in victims.items():
                        for row in rows:
                            stream.write(
                                json.dumps({"table": table, "row": row["data"]}, ensure_ascii=False)
                                + "\n"
                            )
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                backup.unlink(missing_ok=True)
                raise
            # Publish the path only after the backup has been flushed to disk.
            progress(
                {"phase": "cleaning", "backup_path": str(backup), "scanned": 0, "total": total}
            )
        deleted: dict[str, int] = {}
        for table, rows in victims.items():
            if not rows:
                deleted[table] = 0
                continue
            cur.execute(
                sql.SQL("DELETE FROM octop_memory.{} WHERE namespace = %s AND id = ANY(%s)").format(
                    sql.Identifier(table)
                ),
                (namespace, [row["id"] for row in rows]),
            )
            deleted[table] = cur.rowcount
        # The connection context commits both tables together. Any error rolls
        # everything back; the flushed backup is retained for inspection.
    return {
        "backend": "postgres",
        "operation": "namespace_cleanup",
        "namespace": namespace,
        "candidates_deleted": deleted["candidates"],
        "journal_deleted": deleted["journal"],
        "total_deleted": sum(deleted.values()),
        "limit_per_table": LIMIT_PER_TABLE,
        "backup_path": str(backup) if total else None,
        "backup_bytes": backup.stat().st_size if total else 0,
        "physical_space_reclaimed": False,
    }
