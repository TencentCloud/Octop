"""SQLite snapshot helpers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from octop.infra.db.pool import DatabasePool, SqlitePool
from octop.infra.db.repos._base import now_ts

_JWT_SECRET_KEY = "jwt"

# Tables that carry a ``user_id`` ownership column (001_initial schema).
_OWNERSHIP_TABLES = (
    "agents",
    "channels",
    "cron_jobs",
    "sessions",
    "threads",
    "connectors",
    "connector_oauth_states",
    "usage_log",
)


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


def upsert_users_into_pool(pool: DatabasePool, users: list[tuple[object, ...]]) -> None:
    """Insert or update *users* without deleting other rows.

    Used before ownership remapping so the target owner row exists for FKs.
    """
    if not users:
        return
    set_clause = ", ".join(f"{col} = ?" for col in _USER_COLUMNS[1:])
    dialect = pool.dialect
    with pool.transaction() as conn:
        for row in users:
            pk = row[0]
            rest = row[1:]
            cur = conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*rest, pk))
            if dialect == "sqlite":
                updated = int(conn.execute("SELECT changes()").fetchone()[0]) > 0
            else:
                updated = int(getattr(cur, "rowcount", 0) or 0) > 0
            if not updated:
                conn.execute(
                    f"INSERT INTO users({_USER_COLS_SQL}) VALUES ({_USER_PLACEHOLDERS})",
                    row,
                )


def prune_users_not_in(pool: DatabasePool, saved_ids: list[object]) -> None:
    """Delete users whose id is not in *saved_ids*."""
    if not saved_ids:
        return
    placeholders = ", ".join("?" for _ in saved_ids)
    with pool.transaction() as conn:
        conn.execute(f"DELETE FROM users WHERE id NOT IN ({placeholders})", saved_ids)


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
       rows from the backup.  Callers that remap ownership must remassign
       children to a saved user **before** this prune step.
    """
    if not users:
        return
    upsert_users_into_pool(pool, users)
    prune_users_not_in(pool, [row[0] for row in users])


def infer_owner_user_id(users: list[tuple[object, ...]]) -> int | None:
    """Pick a restore owner: first admin, else first saved user."""
    if not users:
        return None
    role_idx = _USER_COLUMNS.index("role")
    for row in users:
        if str(row[role_idx]) == "admin":
            return int(str(row[0]))
    return int(str(users[0][0]))


def _table_has_column(conn: object, table: str, column: str, *, dialect: str) -> bool:
    if dialect == "postgresql":
        row = conn.execute(  # type: ignore[attr-defined]
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ? AND column_name = ?",
            (table, column),
        ).fetchone()
        return row is not None
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # type: ignore[attr-defined]
    return any(str(r[1]) == column for r in rows)


def _table_exists(conn: object, table: str, *, dialect: str) -> bool:
    if dialect == "postgresql":
        row = conn.execute(  # type: ignore[attr-defined]
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = ?",
            (table,),
        ).fetchone()
        return row is not None
    row = conn.execute(  # type: ignore[attr-defined]
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _rewrite_session_key(session_key: str, *, old_uid: int, new_uid: int) -> str:
    """Rewrite dashboard/cli subject segment ``agent:channel:subject:chat``."""
    parts = session_key.split(":", 3)
    if len(parts) != 4:
        return session_key
    agent_id, channel_type, subject, chat_type = parts
    if channel_type not in ("dashboard", "cli"):
        return session_key
    if subject != str(old_uid):
        return session_key
    return f"{agent_id}:{channel_type}:{new_uid}:{chat_type}"


def _patch_channel_metadata(raw: object, *, old_uid: int, new_uid: int) -> str | None:
    if raw is None:
        return None
    try:
        meta = json.loads(str(raw)) if not isinstance(raw, dict) else dict(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict):
        return None
    changed = False
    if meta.get("user_id") == old_uid or meta.get("user_id") == str(old_uid):
        meta["user_id"] = new_uid
        changed = True
    if meta.get("to_handle") == str(old_uid):
        meta["to_handle"] = str(new_uid)
        changed = True
    if not changed:
        return None
    return json.dumps(meta, ensure_ascii=False)


def remap_ownership_to_user(pool: DatabasePool, owner_user_id: int) -> dict[str, int]:
    """Reassign all user-scoped rows to *owner_user_id* (LightClaw migration import).

    Also rewrites dashboard/cli ``session_key`` / ``channel_subject_id`` and
    patches ``channel_metadata.user_id`` when they encode the old Octop user id.

    Caller must ensure *owner_user_id* already exists in ``users`` before
    invoking this (so FK checks succeed), and should prune leftover backup
    users afterwards.
    """
    dialect = pool.dialect
    remapped_tables = 0
    rewritten_keys = 0
    with pool.transaction() as conn:
        old_ids: set[int] = set()
        for table in _OWNERSHIP_TABLES:
            if not _table_exists(conn, table, dialect=dialect):
                continue
            if not _table_has_column(conn, table, "user_id", dialect=dialect):
                continue
            rows = conn.execute(
                f"SELECT DISTINCT user_id FROM {table} WHERE user_id IS NOT NULL"
            ).fetchall()
            for row in rows:
                old_ids.add(int(row[0]))
        old_ids.discard(int(owner_user_id))
        if not old_ids:
            return {"tables": 0, "old_user_ids": 0, "session_keys": 0}

        for old_uid in sorted(old_ids):
            for table in _OWNERSHIP_TABLES:
                if not _table_exists(conn, table, dialect=dialect):
                    continue
                if not _table_has_column(conn, table, "user_id", dialect=dialect):
                    continue
                conn.execute(
                    f"UPDATE {table} SET user_id = ? WHERE user_id = ?",
                    (owner_user_id, old_uid),
                )
                remapped_tables += 1

            # Dashboard / CLI session keys embed the Octop user id as subject.
            if _table_exists(conn, "sessions", dialect=dialect):
                session_rows = conn.execute(
                    "SELECT session_key, channel_type, channel_subject_id, channel_metadata "
                    "FROM sessions WHERE channel_type IN ('dashboard', 'cli') "
                    "AND channel_subject_id = ?",
                    (str(old_uid),),
                ).fetchall()
                for srow in session_rows:
                    old_key = str(srow[0])
                    new_key = _rewrite_session_key(old_key, old_uid=old_uid, new_uid=owner_user_id)
                    new_meta = _patch_channel_metadata(
                        srow[3], old_uid=old_uid, new_uid=owner_user_id
                    )
                    if new_key != old_key:
                        conn.execute(
                            "UPDATE sessions SET session_key = ?, channel_subject_id = ? "
                            "WHERE session_key = ?",
                            (new_key, str(owner_user_id), old_key),
                        )
                        if _table_exists(conn, "threads", dialect=dialect):
                            conn.execute(
                                "UPDATE threads SET session_key = ? WHERE session_key = ?",
                                (new_key, old_key),
                            )
                        if _table_exists(conn, "cron_jobs", dialect=dialect):
                            conn.execute(
                                "UPDATE cron_jobs SET session_key = ? WHERE session_key = ?",
                                (new_key, old_key),
                            )
                        rewritten_keys += 1
                    if new_meta is not None:
                        conn.execute(
                            "UPDATE sessions SET channel_metadata = ? WHERE session_key = ?",
                            (new_meta, new_key if new_key != old_key else old_key),
                        )

    return {
        "tables": remapped_tables,
        "old_user_ids": len(old_ids),
        "session_keys": rewritten_keys,
    }


def capture_jwt_secret_from_pool(pool: DatabasePool) -> bytes | None:
    """Return the live instance JWT secret, or ``None`` if not yet seeded."""
    with pool.connect() as conn:
        row = conn.execute(
            "SELECT v FROM secrets WHERE k = ?",
            (_JWT_SECRET_KEY,),
        ).fetchone()
    if row is None:
        return None
    return bytes(row["v"])


def restore_jwt_secret_into_pool(pool: DatabasePool, secret: bytes) -> None:
    """Write *secret* into ``secrets.jwt`` (insert or overwrite).

    Used after a migration restore so outstanding browser sessions remain valid.
    Does not bump ``rotated_at`` — this is a preserve, not an admin rotation.
    """
    with pool.transaction() as conn:
        row = conn.execute(
            "SELECT 1 FROM secrets WHERE k = ?",
            (_JWT_SECRET_KEY,),
        ).fetchone()
        if row is not None:
            conn.execute(
                "UPDATE secrets SET v = ? WHERE k = ?",
                (secret, _JWT_SECRET_KEY),
            )
        else:
            conn.execute(
                "INSERT INTO secrets(k, v, created_at) VALUES (?, ?, ?)",
                (_JWT_SECRET_KEY, secret, now_ts()),
            )
