"""Apply numbered SQL migrations.

Each file is ``NNN_description.sql`` (SQLite) or ``NNN_description.pg.sql``
(PostgreSQL). Version is stored in ``_schema_version``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from octop.infra.db.pool import DatabasePool

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_SQL_STMT_RE = re.compile(r";\s*\n")


def _split_pg_sql(sql: str) -> list[str]:
    parts = [p.strip() for p in _SQL_STMT_RE.split(sql)]
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        # Drop leading full-line comments so header+DDL blocks are kept.
        lines = part.splitlines()
        while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
            lines.pop(0)
        cleaned = "\n".join(lines).strip()
        if cleaned:
            out.append(cleaned)
    return out


def _discover(dialect: str = "sqlite") -> list[tuple[int, Path]]:
    out: list[tuple[int, Path]] = []
    if not _MIGRATIONS_DIR.exists():
        return out
    for entry in sorted(_MIGRATIONS_DIR.iterdir()):
        name = entry.name
        if dialect == "postgresql":
            m = re.match(r"^(\d{3})_.*\.pg\.sql$", name)
        else:
            if name.endswith(".pg.sql"):
                continue
            m = re.match(r"^(\d{3})_.*\.sql$", name)
        if m:
            out.append((int(m.group(1)), entry))
    return out


def _current_version(db: DatabasePool) -> int:
    with db.connect() as conn:
        try:
            row = conn.execute("SELECT version FROM _schema_version").fetchone()
            if row is None:
                return 0
            version = row["version"] if isinstance(row, Mapping) else row[0]
            return int(version)
        except Exception:
            return 0


def _table_columns(db: DatabasePool, table: str) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _table_exists(db: DatabasePool, table: str) -> bool:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
    return row is not None


def _ensure_column(db: DatabasePool, table: str, column: str, definition: str) -> None:
    """Add a missing column on databases created by older Octop builds."""
    if column in _table_columns(db, table):
        return
    with db.connect() as conn:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_skill_packages_table(db: DatabasePool) -> None:
    """Create skill_packages if missing (idempotent for partial / renamed upgrades)."""
    if _table_exists(db, "skill_packages"):
        return
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TABLE skill_packages (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              created_by TEXT NOT NULL,
              skill_count INTEGER NOT NULL DEFAULT 0,
              icon_name TEXT NOT NULL DEFAULT '',
              icon_url TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )


def _ensure_skill_packages_name_unique_index(db: DatabasePool) -> None:
    """Backfill unique package names for DBs that applied v2 before this index existed."""
    if not _table_exists(db, "skill_packages"):
        return
    with db.connect() as conn:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_packages_name ON skill_packages(name)"
        )


def _repair_legacy_schema(db: DatabasePool) -> None:
    """Idempotent compatibility repairs for local databases from old builds."""
    if _table_exists(db, "users"):
        _ensure_column(db, "users", "locale", "TEXT NOT NULL DEFAULT 'zh'")
        _ensure_column(db, "users", "login_failed_count", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(db, "users", "login_locked_until", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(db, "users", "preferences_json", "TEXT NOT NULL DEFAULT '{}'")
    if _table_exists(db, "cron_jobs"):
        _ensure_column(
            db,
            "cron_jobs",
            "task_type",
            "TEXT NOT NULL DEFAULT 'agent' CHECK (task_type IN ('text', 'agent'))",
        )
        _ensure_column(
            db,
            "cron_jobs",
            "mcp_servers",
            "TEXT NOT NULL DEFAULT '[]'",
        )
    if _table_exists(db, "threads"):
        _ensure_column(db, "threads", "model_ref", "TEXT")
        _ensure_column(db, "threads", "reasoning_mode", "TEXT")
        _ensure_column(db, "threads", "reasoning_effort", "TEXT")
    _ensure_skill_packages_table(db)
    if _table_exists(db, "skill_packages"):
        _ensure_column(db, "skill_packages", "icon_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(db, "skill_packages", "icon_url", "TEXT NOT NULL DEFAULT ''")
        _ensure_skill_packages_name_unique_index(db)


def _apply_postgresql_migration(conn: Any, sql: str) -> None:
    for stmt in _split_pg_sql(sql):
        conn.execute(stmt)


def _apply_sqlite_migration(db: DatabasePool, version: int, path: Path) -> None:
    """Apply one SQLite migration.

    Version 2 uses ``_ensure_column`` / table helpers so re-running after a
    partial upgrade does not fail.

    Version 3 bumps schema then rewrites legacy hard-cut thread titles in Python.
    Version 4 adds composer columns idempotently after legacy schema repair.
    """
    if version == 2:
        if _table_exists(db, "cron_jobs"):
            _ensure_column(
                db,
                "cron_jobs",
                "mcp_servers",
                "TEXT NOT NULL DEFAULT '[]'",
            )
        _ensure_skill_packages_table(db)
        if _table_exists(db, "skill_packages"):
            _ensure_column(db, "skill_packages", "icon_name", "TEXT NOT NULL DEFAULT ''")
            _ensure_column(db, "skill_packages", "icon_url", "TEXT NOT NULL DEFAULT ''")
            _ensure_skill_packages_name_unique_index(db)
        with db.connect() as conn:
            conn.execute("UPDATE _schema_version SET version = ?", (version,))
        return
    if version == 3:
        with db.connect() as conn:
            conn.execute("UPDATE _schema_version SET version = ?", (version,))
        if _table_exists(db, "threads"):
            from octop.infra.db.repos.threads import repair_all_legacy_thread_titles

            repair_all_legacy_thread_titles(db)
        return
    if version == 4:
        if _table_exists(db, "threads"):
            _ensure_column(db, "threads", "model_ref", "TEXT")
            _ensure_column(db, "threads", "reasoning_mode", "TEXT")
            _ensure_column(db, "threads", "reasoning_effort", "TEXT")
        with db.connect() as conn:
            conn.execute("UPDATE _schema_version SET version = ?", (version,))
        return
    sql = path.read_text(encoding="utf-8")
    with db.connect() as conn:
        conn.executescript(sql)


def run_migrations(db: DatabasePool) -> None:
    if db.dialect == "sqlite":
        _repair_legacy_schema(db)
    for version, path in _discover(db.dialect):
        if version <= _current_version(db):
            continue
        if db.dialect == "postgresql":
            sql = path.read_text(encoding="utf-8")
            with db.connect() as conn, conn.transaction():
                _apply_postgresql_migration(conn, sql)
            if version == 3:
                from octop.infra.db.repos.threads import repair_all_legacy_thread_titles

                repair_all_legacy_thread_titles(db)
        else:
            _apply_sqlite_migration(db, version, path)
