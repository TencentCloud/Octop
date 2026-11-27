"""Restore a dedicated SQLite memory file after its runtime has been drained."""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import time
import uuid
from collections.abc import Callable
from contextlib import closing, suppress
from pathlib import Path
from typing import Any

from octop.i18n import tr


def backup_path(path: Path, backup_id: str, locale: str) -> Path:
    pattern = (
        re.escape(path.name) + r"(?:\.before-(?:slim|restore)\.[0-9a-f]{32}\.bak|\.pre-prune\.bak)"
    )
    candidate = path.parent / backup_id
    if not re.fullmatch(pattern, backup_id) or candidate.is_symlink() or not candidate.is_file():
        raise ValueError(tr("memory_storage.invalid_backup", locale))
    return candidate


def list_backups(path: Path) -> list[dict[str, Any]]:
    result = []
    candidates = list(path.parent.glob(f"{path.name}.before-*.bak"))
    pre_prune = path.with_name(f"{path.name}.pre-prune.bak")
    if pre_prune.is_file():
        candidates.append(pre_prune)
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.name in seen:
            continue
        seen.add(candidate.name)
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


def _is_healthy_foreign_target(conn: sqlite3.Connection, namespace: str) -> bool:
    """True when *conn* is an intact SQLite database belonging to another expert."""
    try:
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            return False
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    except sqlite3.Error:
        return False
    namespaces = {
        name.removesuffix("_raw_events") for name in tables if name.endswith("_raw_events")
    }
    return bool(namespaces) and namespaces != {namespace}


def _fsync_file(target: Path) -> None:
    # Windows requires a writable handle for fsync.
    with target.open("r+b") as handle:
        os.fsync(handle.fileno())


def _remove_wal_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        with suppress(OSError):
            path.with_name(path.name + suffix).unlink(missing_ok=True)


def _replace_corrupt_sqlite(
    src: sqlite3.Connection,
    path: Path,
    namespace: str,
    *,
    locale: str,
    progress: Callable[[dict[str, Any]], None],
) -> tuple[Path, int]:
    """Archive a corrupted target file and atomically swap in a verified copy of *src*."""
    token = uuid.uuid4().hex
    corrupt_backup = path.with_name(f"{path.name}.corrupt-before-restore.{token}.bak")
    staging = path.with_name(f"{path.name}.restoring.{token}.tmp")
    progress({"phase": "backing_up_current"})
    try:
        shutil.copy2(path, corrupt_backup)
        if os.name == "posix":
            os.chmod(corrupt_backup, 0o600)
        _fsync_file(corrupt_backup)
        wal = path.with_name(path.name + "-wal")
        if wal.is_file():
            with suppress(OSError):
                shutil.copy2(wal, corrupt_backup.with_name(corrupt_backup.name + "-wal"))
    except BaseException:
        corrupt_backup.unlink(missing_ok=True)
        raise

    progress({"phase": "restoring", "backup_path": str(corrupt_backup)})
    fd = os.open(staging, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with closing(sqlite3.connect(staging, timeout=5)) as staged:
            src.backup(staged)
            _validate(staged, namespace, locale)
            staged.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        _remove_wal_sidecars(staging)
        _fsync_file(staging)
        _remove_wal_sidecars(path)
        os.replace(staging, path)
    except BaseException:
        _remove_wal_sidecars(staging)
        staging.unlink(missing_ok=True)
        raise
    return corrupt_backup, corrupt_backup.stat().st_size


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
    When the current target is already corrupted, archive the broken bytes and
    atomically replace the file with a validated copy of the backup instead of
    aborting on target validation.
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

        target_corrupt = False
        try:
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)) as probe:
                probe.execute("PRAGMA query_only=ON")
                try:
                    _validate(probe, namespace, locale)
                except (sqlite3.DatabaseError, ValueError):
                    if _is_healthy_foreign_target(probe, namespace):
                        raise
                    target_corrupt = True
        except sqlite3.DatabaseError:
            target_corrupt = True

        if target_corrupt:
            corrupt_backup, backup_bytes = _replace_corrupt_sqlite(
                src, path, namespace, locale=locale, progress=progress
            )
            return {
                "backend": "sqlite",
                "operation": "restore",
                "restored_backup_id": backup_id,
                "backup_path": str(corrupt_backup),
                "backup_bytes": backup_bytes,
                "recovered_corrupt_target": True,
                "elapsed_ms": (time.perf_counter() - started) * 1000,
            }

        with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)) as dest:
            progress({"phase": "backing_up_current"})
            fd = os.open(safety, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            try:
                with closing(sqlite3.connect(safety)) as saved:
                    dest.backup(saved)
                    _validate(saved, namespace, locale)
                _fsync_file(safety)
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
