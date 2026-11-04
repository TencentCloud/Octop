"""Read-only, bounded SQLite diagnostics for one expert's memory store."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

MEMORY_TABLES = (
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
CHECKPOINT_TABLES = ("checkpoints", "writes", "hm_checkpoint_blobs")
COUNT_BUDGET_SECONDS = 5.0


def inspect_sqlite_storage(backend: Any, *, shared: bool) -> dict[str, Any]:
    """Use a separate read-only snapshot; never initialize or migrate a store.

    Unprefixed checkpoint tables cannot be attributed to an expert in a shared
    file. In that case return only the selected namespace's memory counts.
    """
    started = time.perf_counter()
    path = Path(backend._db_path).expanduser().resolve(strict=True)
    namespace = str(backend._ns)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        names = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        # Also detect residual namespaces that no longer have a registry row.
        shared = shared or any(
            name.endswith("_raw_events") and name != f"{namespace}_raw_events" for name in names
        )
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        pages = conn.execute("PRAGMA page_count").fetchone()[0]
        free = conn.execute("PRAGMA freelist_count").fetchone()[0]
        auto_vacuum = conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2
        wal = Path(str(path) + "-wal")
        try:
            wal_size = wal.stat().st_size
        except FileNotFoundError:
            wal_size = 0
        report: dict[str, Any] = {
            "file_size": path.stat().st_size,
            "wal_size": wal_size,
            "page_size": page_size,
            "total_pages": pages,
            "freelist_pages": free,
            "reclaimable_bytes": free * page_size,
            "auto_vacuum_enabled": auto_vacuum,
            "file_check_ms": (time.perf_counter() - started) * 1000,
            "namespace": namespace,
            "checkpoints_available": not shared,
        }
        deadline = time.perf_counter() + COUNT_BUDGET_SECONDS
        conn.set_progress_handler(lambda: int(time.perf_counter() >= deadline), 1000)

        def count(label: str, table: str, expression: str = "count(*)") -> dict[str, Any]:
            begin = time.perf_counter()
            rows = None
            status = "missing"
            if table in names:
                status = "timed_out"
                if begin < deadline:
                    quoted = '"' + table.replace('"', '""') + '"'
                    try:
                        rows = conn.execute(f"SELECT {expression} FROM {quoted}").fetchone()[0]
                        status = "ok"
                    except sqlite3.OperationalError as exc:
                        if str(exc) != "interrupted":
                            raise
            return {
                "table": label,
                "rows": rows,
                "status": status,
                "elapsed_ms": (time.perf_counter() - begin) * 1000,
            }

        report["memory_counts"] = [count(name, f"{namespace}_{name}") for name in MEMORY_TABLES]
        report["checkpoint_counts"] = (
            [count(name, name) for name in CHECKPOINT_TABLES]
            + [count("checkpoint_threads", "checkpoints", "count(DISTINCT thread_id)")]
            if not shared
            else []
        )
        conn.set_progress_handler(None, 0)
        conn.rollback()
    report["elapsed_ms"] = (time.perf_counter() - started) * 1000
    return report
