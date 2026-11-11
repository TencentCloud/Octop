"""Restore a dedicated SQLite memory file after its runtime has been drained."""

from __future__ import annotations

import os
import re
import sqlite3
import time
import uuid
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

from octop.i18n import tr


def backup_path(path: Path, backup_id: str, locale: str) -> Path:
    pattern = re.escape(path.name) + r"\.before-(?:slim|restore)\.[0-9a-f]{32}\.bak"
    candidate = path.parent / backup_id
    if not re.fullmatch(pattern, backup_id) or candidate.is_symlink() or not candidate.is_file():
        raise ValueError(tr("memory_storage.invalid_backup", locale))
    return candidate


def list_backups(path: Path) -> list[dict[str, Any]]:
    result = []
    for candidate in path.parent.glob(f"{path.name}.before-*.bak"):
        try:
            backup_path(path, candidate.name, "en")
            stat = candidate.stat()
        except (ValueError, OSError):
            continue
        result.append(
            {
                "backup_id": candidate.name,
                "created_at": stat.st_mtime,
                "size_bytes": stat.st_size,
                "kind": "before_restore"
                if ".before-restore." in candidate.name
                else "before_maintenance",
            }
        )
    return sorted(result, key=lambda item: item["created_at"], reverse=True)


def delete_backup(path: Path, backup_id: str, locale: str) -> None:
    """Delete one eligible sibling backup, never the active database."""
    candidate = backup_path(path, backup_id, locale)
    try:
        candidate.unlink()
    except OSError as exc:
        raise ValueError(tr("memory_storage.delete_backup_failed", locale)) from exc


def _validate(conn: sqlite3.Connection, namespace: str, locale: str) -> None:
    from octop_memory.storage.backends.sqlite_checkpoint import CompactSqliteSaver

    if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise ValueError(tr("memory_storage.invalid_backup", locale))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    namespaces = {
        name.removesuffix("_raw_events") for name in tables if name.endswith("_raw_events")
    }
    if namespaces != {namespace} or not {"checkpoints", "writes"}.issubset(tables):
        raise ValueError(tr("memory_storage.backup_scope", locale))
    # Check reference payloads as well as SQLite pages before overwriting anything.
    codec = CompactSqliteSaver(conn).codec
    for kind, value in conn.execute("SELECT type, checkpoint FROM checkpoints"):
        codec.loads_typed((kind, value))


def restore_sqlite(
    path: Path,
    namespace: str,
    backup_id: str,
    *,
    locale: str,
    progress: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Validate, snapshot current data durably, then use SQLite's backup API.

    Restore in-place so WAL and any idle read handles remain SQLite-managed.
    No path supplied by the client is accepted; backups must be regular siblings
    matching the host's backup naming scheme and the exact memory namespace.
    """
    source = backup_path(path, backup_id, locale)
    safety = path.with_name(f"{path.name}.before-restore.{uuid.uuid4().hex}.bak")
    started = time.perf_counter()
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)) as src:
        src.execute("PRAGMA query_only=ON")
        src.execute("BEGIN")
        progress({"phase": "validating"})
        _validate(src, namespace, locale)
        with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)) as dest:
            _validate(dest, namespace, locale)
            progress({"phase": "backing_up_current"})
            fd = os.open(safety, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            try:
                with closing(sqlite3.connect(safety)) as saved:
                    dest.backup(saved)
                    _validate(saved, namespace, locale)
                # Windows requires a writable handle for fsync. Do not truncate
                # the snapshot: it must be durable before overwriting the store.
                with safety.open("r+b") as saved_file:
                    os.fsync(saved_file.fileno())
            except BaseException:
                safety.unlink(missing_ok=True)
                raise
            progress({"phase": "restoring", "backup_path": str(safety)})
            try:
                src.backup(dest)
                _validate(dest, namespace, locale)
            except BaseException:
                # The host has stopped all writers; restoring this snapshot cannot
                # discard writes made after it. Always retain it for manual recovery.
                with closing(sqlite3.connect(safety.as_uri() + "?mode=ro", uri=True)) as saved:
                    saved.backup(dest)
                raise
            dest.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return {
        "backend": "sqlite",
        "operation": "restore",
        "restored_backup_id": backup_id,
        "backup_path": str(safety),
        "backup_bytes": safety.stat().st_size,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }
