"""SQLite snapshot helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

from octop.infra.db.pool import SqlitePool


def _readonly_sqlite_uri(path: Path) -> str:
    """Build a read-only SQLite URI with a percent-encoded filesystem path."""
    encoded = quote(path.resolve().as_posix(), safe="/:")
    return f"file:{encoded}?mode=ro"


def snapshot_sqlite_file(source: Path, dest: Path) -> None:
    """Copy *source* into *dest* using SQLite's online backup API."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(_readonly_sqlite_uri(source), uri=True)
    try:
        dest_conn = sqlite3.connect(dest)
        try:
            src.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src.close()


def restore_sqlite_file(backup_file: Path, target: Path) -> None:
    """Replace on-disk *target* with *backup_file* (server should be stopped)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(_readonly_sqlite_uri(backup_file), uri=True)
    try:
        dest = sqlite3.connect(target)
        try:
            src.backup(dest)
            dest.execute("PRAGMA wal_checkpoint(FULL)")
        finally:
            dest.close()
    finally:
        src.close()


def restore_sqlite_into_pool(backup_file: Path, pool: SqlitePool) -> None:
    """Merge a backup file into the live pooled connection."""
    src = sqlite3.connect(_readonly_sqlite_uri(backup_file), uri=True)
    try:
        with pool.connect() as live:
            src.backup(live)
            live.execute("PRAGMA wal_checkpoint(FULL)")
    finally:
        src.close()
