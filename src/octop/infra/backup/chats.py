"""Chat-history tables and workspace paths excluded from default backups."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from octop.infra.agents.workspace_dir import DEFAULT_SYSTEM_FILES_PATH
from octop.infra.backup.snapshot import _patch_channel_metadata, _rewrite_session_key
from octop.infra.db.pool import DatabasePool

# Child-first for DELETE; reverse for INSERT.
CHAT_TABLES_CHILD_FIRST = (
    "trajectory_events",
    "thread_messages",
    "thread_history_projection",
    "threads",
    "sessions",
)
CHAT_TABLES_PARENT_FIRST = tuple(reversed(CHAT_TABLES_CHILD_FIRST))

_CHAT_DIR_NAMES = frozenset({"sessions", "conversation_history"})
_CHAT_FILE_NAMES = frozenset(
    {
        "checkpoints.sqlite",
        "checkpoints.sqlite-wal",
        "checkpoints.sqlite-shm",
        "memory.sqlite",
        "memory.sqlite-wal",
        "memory.sqlite-shm",
    }
)
_USERS_SPOOL_TABLE = "_users"


def is_chat_workspace_rel(rel: Path, *, system_files_path: str = "") -> bool:
    """Return True when *rel* is session logs / checkpoints / offloaded history.

    When *system_files_path* is empty, skip both workspace-root chat dirs
    (legacy layout) and ``.octop/`` (current default).
    """
    prefixes = (
        (system_files_path,) if system_files_path.strip() else ("", DEFAULT_SYSTEM_FILES_PATH)
    )
    return any(_matches_chat_under_prefix(rel, prefix) for prefix in prefixes)


def _matches_chat_under_prefix(rel: Path, prefix: str) -> bool:
    parts = rel.parts
    prefix_parts = Path(prefix).parts if prefix else ()
    if prefix_parts:
        if parts[: len(prefix_parts)] != prefix_parts:
            return False
        rest = parts[len(prefix_parts) :]
    else:
        rest = parts
    if not rest:
        return False
    if rest[0] in _CHAT_DIR_NAMES:
        return True
    return len(rest) == 1 and rest[0] in _CHAT_FILE_NAMES


def strip_chat_tables_from_sqlite_file(path: Path) -> None:
    """Empty chat tables in a SQLite snapshot and reclaim pages with VACUUM."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        existing = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for table in CHAT_TABLES_CHILD_FIRST:
            if table in existing:
                conn.execute(f"DELETE FROM {table}")
        if "sqlite_sequence" in existing:
            placeholders = ", ".join("?" for _ in CHAT_TABLES_CHILD_FIRST)
            conn.execute(
                f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})",
                CHAT_TABLES_CHILD_FIRST,
            )
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()


def capture_chat_tables(pool: DatabasePool, dest: Path) -> Path:
    """Stream live chat rows into a temporary SQLite spool file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    spool = sqlite3.connect(dest)
    try:
        with pool.connect() as conn:
            _spool_users(conn, spool, dialect=pool.dialect)
            for table in CHAT_TABLES_PARENT_FIRST:
                if not _table_exists(conn, table, dialect=pool.dialect):
                    continue
                cursor = conn.execute(f"SELECT * FROM {table}")
                columns = _cursor_columns(cursor)
                if not columns:
                    continue
                quoted_columns = ", ".join(f'"{_quote_identifier(col)}" BLOB' for col in columns)
                spool.execute(f'CREATE TABLE "{table}" ({quoted_columns})')
                placeholders = ", ".join("?" for _ in columns)
                while rows := cursor.fetchmany(500):
                    spool.executemany(
                        f'INSERT INTO "{table}" VALUES ({placeholders})',
                        [tuple(row[col] for col in columns) for row in rows],
                    )
        spool.commit()
    finally:
        spool.close()
    return dest


def restore_preserved_chats(pool: DatabasePool, spool_path: Path) -> tuple[int, int]:
    """Replace restored chat tables with rows streamed from *spool_path*.

    ``user_id`` is remapped by username when the restored ``users`` table uses
    different integer ids. Rows whose agent or user cannot be resolved are
    skipped. Returns ``(inserted, skipped)``.
    """
    inserted = 0
    skipped = 0
    dialect = pool.dialect
    spool = sqlite3.connect(spool_path)
    try:
        old_id_to_name = _load_spooled_users(spool)
        with pool.transaction() as conn:
            agent_ids = _id_set(conn, "agents", "agent_id", dialect=dialect)
            new_name_to_id = _load_live_usernames(conn, dialect=dialect)

            for table in CHAT_TABLES_CHILD_FIRST:
                if _table_exists(conn, table, dialect=dialect):
                    conn.execute(f"DELETE FROM {table}")

            kept_threads: set[str] = set()
            for table in CHAT_TABLES_PARENT_FIRST:
                columns = _spool_columns(spool, table)
                if not columns or not _table_exists(conn, table, dialect=dialect):
                    continue
                col_index = {name: i for i, name in enumerate(columns)}
                placeholders = ", ".join("?" for _ in columns)
                col_sql = ", ".join(columns)
                insert_sql = f"INSERT INTO {table}({col_sql}) VALUES ({placeholders})"
                cursor = spool.execute(f'SELECT * FROM "{table}"')
                while rows := cursor.fetchmany(500):
                    batch: list[tuple[object, ...]] = []
                    for row in rows:
                        mapped = _remap_chat_row(
                            table,
                            tuple(row),
                            col_index,
                            agent_ids=agent_ids,
                            old_id_to_name=old_id_to_name,
                            new_name_to_id=new_name_to_id,
                            kept_threads=kept_threads,
                        )
                        if mapped is None:
                            skipped += 1
                            continue
                        batch.append(mapped)
                        if table == "threads" and "thread_id" in col_index:
                            kept_threads.add(str(mapped[col_index["thread_id"]]))
                    if batch:
                        conn.executemany(insert_sql, batch)
                        inserted += len(batch)
                _sync_chat_id_sequence(conn, table, dialect=dialect)
    finally:
        spool.close()
    return inserted, skipped


def _spool_users(src: Any, spool: sqlite3.Connection, *, dialect: str) -> None:
    if not _table_exists(src, "users", dialect=dialect):
        return
    spool.execute(f'CREATE TABLE "{_USERS_SPOOL_TABLE}" (id BLOB, username BLOB)')
    rows = src.execute("SELECT id, username FROM users").fetchall()
    if rows:
        spool.executemany(
            f'INSERT INTO "{_USERS_SPOOL_TABLE}" VALUES (?, ?)',
            [(row[0], row[1]) for row in rows],
        )


def _cursor_columns(cursor: Any) -> list[str]:
    description = cursor.description or ()
    columns: list[str] = []
    for item in description:
        name = getattr(item, "name", None)
        columns.append(str(name if name is not None else item[0]))
    return columns


def _quote_identifier(value: str) -> str:
    return value.replace('"', '""')


def _spool_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if exists is None:
        return []
    return [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def _table_exists(conn: Any, table: str, *, dialect: str) -> bool:
    if dialect == "postgresql":
        row = conn.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = ?",
            (table,),
        ).fetchone()
        return row is not None
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: Any, table: str, column: str, *, dialect: str) -> bool:
    if dialect == "postgresql":
        row = conn.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ? AND column_name = ?",
            (table, column),
        ).fetchone()
        return row is not None
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(r[1]) == column for r in rows)


def _id_set(conn: Any, table: str, column: str, *, dialect: str) -> set[object]:
    if not _table_exists(conn, table, dialect=dialect):
        return set()
    rows = conn.execute(f"SELECT {column} FROM {table}").fetchall()
    return {row[0] for row in rows}


def _load_spooled_users(spool: sqlite3.Connection) -> dict[int, str]:
    if not _spool_columns(spool, _USERS_SPOOL_TABLE):
        return {}
    out: dict[int, str] = {}
    for row in spool.execute(f'SELECT id, username FROM "{_USERS_SPOOL_TABLE}"').fetchall():
        try:
            out[int(row[0])] = str(row[1])
        except (TypeError, ValueError):
            continue
    return out


def _load_live_usernames(conn: Any, *, dialect: str) -> dict[str, int]:
    if not _table_exists(conn, "users", dialect=dialect):
        return {}
    out: dict[str, int] = {}
    for row in conn.execute("SELECT id, username FROM users").fetchall():
        try:
            out[str(row[1])] = int(row[0])
        except (TypeError, ValueError):
            continue
    return out


def _map_user_id(
    old_uid: object,
    old_id_to_name: dict[int, str],
    new_name_to_id: dict[str, int],
) -> int | None:
    try:
        old = int(str(old_uid))
    except (TypeError, ValueError):
        return None
    name = old_id_to_name.get(old)
    if name and name in new_name_to_id:
        return new_name_to_id[name]
    return None


def _remap_chat_row(
    table: str,
    row: tuple[object, ...],
    col_index: dict[str, int],
    *,
    agent_ids: set[object],
    old_id_to_name: dict[int, str],
    new_name_to_id: dict[str, int],
    kept_threads: set[str],
) -> tuple[object, ...] | None:
    if "agent_id" in col_index and row[col_index["agent_id"]] not in agent_ids:
        return None
    values = list(row)
    old_uid: int | None = None
    new_uid: int | None = None
    if "user_id" in col_index:
        old_raw = values[col_index["user_id"]]
        try:
            old_uid = int(str(old_raw))
        except (TypeError, ValueError):
            return None
        new_uid = _map_user_id(old_uid, old_id_to_name, new_name_to_id)
        if new_uid is None:
            return None
        values[col_index["user_id"]] = new_uid
        if old_uid != new_uid:
            _apply_user_id_rewrite(table, values, col_index, old_uid=old_uid, new_uid=new_uid)
    if (
        table in ("trajectory_events", "thread_messages", "thread_history_projection")
        and "thread_id" in col_index
        and str(values[col_index["thread_id"]]) not in kept_threads
    ):
        return None
    return tuple(values)


def _apply_user_id_rewrite(
    table: str,
    values: list[object],
    col_index: dict[str, int],
    *,
    old_uid: int,
    new_uid: int,
) -> None:
    if "session_key" in col_index and values[col_index["session_key"]] is not None:
        values[col_index["session_key"]] = _rewrite_session_key(
            str(values[col_index["session_key"]]),
            old_uid=old_uid,
            new_uid=new_uid,
        )
    if table == "sessions" and "channel_subject_id" in col_index:
        subject = values[col_index["channel_subject_id"]]
        if subject is not None and str(subject) == str(old_uid):
            values[col_index["channel_subject_id"]] = str(new_uid)
    if table == "sessions" and "channel_metadata" in col_index:
        patched = _patch_channel_metadata(
            values[col_index["channel_metadata"]],
            old_uid=old_uid,
            new_uid=new_uid,
        )
        if patched is not None:
            values[col_index["channel_metadata"]] = patched


def _sync_chat_id_sequence(conn: Any, table: str, *, dialect: str) -> None:
    if not _column_exists(conn, table, "id", dialect=dialect):
        return
    if dialect == "postgresql":
        conn.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table}"
        )
        return
    row = conn.execute(f"SELECT MAX(id) FROM {table}").fetchone()
    max_id = row[0] if row is not None else None
    seq_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'"
    ).fetchone()
    if seq_exists is None:
        return
    if max_id is None:
        conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
        return
    current = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = ?",
        (table,),
    ).fetchone()
    if current is None:
        conn.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
            (table, int(max_id)),
        )
    else:
        conn.execute(
            "UPDATE sqlite_sequence SET seq = ? WHERE name = ?",
            (int(max_id), table),
        )
