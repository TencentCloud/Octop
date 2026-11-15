"""Read-only, bounded SQLite diagnostics for one expert's memory store."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

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
_VACUUM_RECOMMEND_BYTES = 32 * 1024 * 1024
_BACKUP_MODE_ENV = "OCTOP_CHECKPOINT_BACKUP_BEFORE_PRUNE"
_BACKUP_KEEP_DAYS_ENV = "OCTOP_CHECKPOINT_BACKUP_KEEP_DAYS"


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() not in {"0", "false", "off", "no"}


def _optional_positive_int(name: str) -> int | None:
    if name not in os.environ:
        return None
    raw = os.environ.get(name, "").strip()
    if not raw or raw == "0":
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


@lru_cache(maxsize=32)
def _parse_backup_mode(value: str) -> Literal["first", "always", "off"]:
    if value in {"", "first"}:
        return "first"
    if value in {"always", "1", "true", "on", "yes"}:
        return "always"
    if value in {"0", "false", "off", "no"}:
        return "off"
    logger.warning("invalid %s=%r; using first", _BACKUP_MODE_ENV, value)
    return "first"


@lru_cache(maxsize=32)
def _parse_backup_keep_days(value: str) -> int:
    if not value:
        return 7
    try:
        days = int(value)
        if days >= 0:
            return days
    except ValueError:
        pass
    logger.warning("invalid %s=%r; using 7", _BACKUP_KEEP_DAYS_ENV, value)
    return 7


def _checkpoint_backup_policy_from_env() -> tuple[Literal["first", "always", "off"], int]:
    # Match Harness maintenance while remaining compatible with older Harness wheels.
    return (
        _parse_backup_mode(os.environ.get(_BACKUP_MODE_ENV, "").strip().lower()),
        _parse_backup_keep_days(os.environ.get(_BACKUP_KEEP_DAYS_ENV, "").strip()),
    )


def _checkpoint_policy(reclaimable_bytes: int) -> dict[str, Any]:
    """Retention window shown on the storage page.

    Matches idle maintenance in octop-harness: keep the newest 20 checkpoints
    unless ``OCTOP_CHECKPOINT_RETENTION`` is turned off.
    """
    keep_last = _optional_positive_int("OCTOP_CHECKPOINT_KEEP_LAST")
    keep_days = _optional_positive_int("OCTOP_CHECKPOINT_KEEP_DAYS")
    if not _env_flag("OCTOP_CHECKPOINT_RETENTION", True):
        keep_last = None
        keep_days = None
    elif "OCTOP_CHECKPOINT_KEEP_LAST" not in os.environ:
        keep_last = 20
    backup_mode, backup_keep_days = _checkpoint_backup_policy_from_env()
    return {
        "checkpoint_retention_enabled": keep_last is not None or keep_days is not None,
        "checkpoint_keep_last": keep_last,
        "checkpoint_keep_days": keep_days,
        "checkpoint_backup_before_prune": backup_mode,
        "checkpoint_backup_keep_days": backup_keep_days,
        "checkpoint_vacuum_recommended": reclaimable_bytes >= _VACUUM_RECOMMEND_BYTES,
    }


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
            **_checkpoint_policy(free * page_size),
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
