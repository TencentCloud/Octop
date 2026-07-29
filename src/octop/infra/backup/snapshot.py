"""SQLite snapshot helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

from octop.infra.db.pool import DatabasePool, SqlitePool


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


# ---------------------------------------------------------------------------
# User helpers for migration restores
# ---------------------------------------------------------------------------

# All columns in the users table (must match schema in 001_initial.sql).
_USER_COLUMNS = (
    "id",
    "username",
    "password_hash",
    "role",
    "display_name",
    "disabled",
    "created_at",
    "locale",
    "preferences_json",
    "login_failed_count",
    "login_locked_until",
)
_USER_COLS_SQL = ", ".join(_USER_COLUMNS)
_USER_PLACEHOLDERS = ", ".join("?" for _ in _USER_COLUMNS)


def capture_users_from_pool(pool: DatabasePool) -> list[tuple[object, ...]]:
    """Return all rows from the live *users* table as plain tuples."""
    with pool.connect() as conn:
        rows = conn.execute(f"SELECT {_USER_COLS_SQL} FROM users").fetchall()
    return [tuple(r) for r in rows]


def restore_users_into_pool(pool: DatabasePool, users: list[tuple[object, ...]]) -> None:
    """Merge *users* (previously captured rows) back into the *users* table.

    Avoids ``DELETE FROM users`` (and ``INSERT OR REPLACE``, which SQLite
    implements as DELETE + INSERT) because both trigger ``ON DELETE CASCADE``
    on child tables (agents, sessions, threads, …) when
    ``PRAGMA foreign_keys = ON`` is active — wiping the data just restored
    from the backup.

    Strategy:
    1. For each saved row: UPDATE in-place if the ``id`` already exists,
       otherwise INSERT.  Neither operation removes the row first, so FK
       children are preserved.
    2. DELETE rows whose ``id`` is not in the saved set — removes leftover
       rows from the backup that are not part of the current instance's users.
       These rows have no children that matter (their children came from the
       backup and reference backup user-ids that are being deleted anyway).
    """
    if not users:
        return
    saved_ids = [row[0] for row in users]  # first column is always ``id``
    # Build SET clause for UPDATE: skip the first column (id is the PK).
    set_clause = ", ".join(f"{col} = ?" for col in _USER_COLUMNS[1:])
    with pool.transaction() as conn:
        for row in users:
            pk = row[0]
            rest = row[1:]
            conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*rest, pk))
            # If no row matched, the id does not exist yet — insert it.
            if conn.execute("SELECT changes()").fetchone()[0] == 0:
                conn.execute(
                    f"INSERT INTO users({_USER_COLS_SQL}) VALUES ({_USER_PLACEHOLDERS})",
                    row,
                )
        # Remove backup-origin rows whose id is not in the saved set.
        placeholders = ", ".join("?" for _ in saved_ids)
        conn.execute(f"DELETE FROM users WHERE id NOT IN ({placeholders})", saved_ids)
