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


def _ensure_published_experts_table(db: DatabasePool) -> None:
    """Create published_experts if missing (idempotent for partial upgrades)."""
    if _table_exists(db, "published_experts"):
        return
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TABLE published_experts (
              id              TEXT PRIMARY KEY,
              slug            TEXT NOT NULL,
              name            TEXT NOT NULL,
              description     TEXT NOT NULL DEFAULT '',
              created_by      TEXT NOT NULL,
              source_agent_id TEXT,
              icon_name       TEXT NOT NULL DEFAULT '',
              color           TEXT NOT NULL DEFAULT '',
              created_at      INTEGER NOT NULL,
              updated_at      INTEGER NOT NULL
            )
            """
        )


def _ensure_published_experts_indexes(db: DatabasePool) -> None:
    if not _table_exists(db, "published_experts"):
        return
    with db.connect() as conn:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_published_experts_slug "
            "ON published_experts(slug)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_published_experts_created_by "
            "ON published_experts(created_by)"
        )


def _ensure_knowledge_bases_schema(db: DatabasePool) -> None:
    """Create knowledge tables / columns idempotently (renumbered local upgrades)."""
    if not _table_exists(db, "knowledge_bases"):
        with db.connect() as conn:
            conn.execute(
                """
                CREATE TABLE knowledge_bases (
                  id TEXT PRIMARY KEY,
                  owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  name TEXT NOT NULL,
                  description TEXT NOT NULL DEFAULT '',
                  default_open INTEGER NOT NULL DEFAULT 0,
                  shared INTEGER NOT NULL DEFAULT 0,
                  icon_name TEXT NOT NULL DEFAULT '',
                  embedding_model TEXT NOT NULL DEFAULT '',
                  embedding_dim INTEGER NOT NULL DEFAULT 0,
                  doc_count INTEGER NOT NULL DEFAULT 0,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL,
                  UNIQUE(owner_user_id, name)
                )
                """
            )
    else:
        _ensure_column(db, "knowledge_bases", "shared", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(db, "knowledge_bases", "icon_name", "TEXT NOT NULL DEFAULT ''")
    with db.connect() as conn:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_bases_owner ON knowledge_bases(owner_user_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_base_members (
              kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              role TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              PRIMARY KEY (kb_id, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_documents (
              id TEXT PRIMARY KEY,
              kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
              filename TEXT NOT NULL,
              content_type TEXT NOT NULL,
              byte_size INTEGER NOT NULL,
              content_hash TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'pending',
              error_message TEXT NOT NULL DEFAULT '',
              chunk_count INTEGER NOT NULL DEFAULT 0,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_documents_kb ON knowledge_documents(kb_id)"
        )


def _repair_legacy_schema(db: DatabasePool) -> None:
    """Idempotent compatibility repairs for local databases from old builds."""
    if _table_exists(db, "users"):
        _ensure_column(db, "users", "locale", "TEXT NOT NULL DEFAULT 'zh'")
        _ensure_column(db, "users", "login_failed_count", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(db, "users", "login_locked_until", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(db, "users", "preferences_json", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(db, "users", "email", "TEXT")
        _ensure_column(db, "users", "sso_provider_id", "INTEGER")
        _ensure_column(db, "users", "sso_subject", "TEXT")
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
    if _table_exists(db, "agents"):
        _ensure_column(db, "agents", "is_shared", "INTEGER NOT NULL DEFAULT 0")
    _ensure_skill_packages_table(db)
    if _table_exists(db, "skill_packages"):
        _ensure_column(db, "skill_packages", "icon_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(db, "skill_packages", "icon_url", "TEXT NOT NULL DEFAULT ''")
        _ensure_skill_packages_name_unique_index(db)
    _ensure_published_experts_table(db)
    _ensure_published_experts_indexes(db)
    if _table_exists(db, "knowledge_bases"):
        _ensure_column(db, "knowledge_bases", "shared", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(db, "knowledge_bases", "icon_name", "TEXT NOT NULL DEFAULT ''")


def _apply_postgresql_migration(conn: Any, sql: str) -> None:
    for stmt in _split_pg_sql(sql):
        conn.execute(stmt)


def _apply_sqlite_migration(db: DatabasePool, version: int, path: Path) -> None:
    """Apply one SQLite migration.

    Version 2 uses ``_ensure_column`` / table helpers so re-running after a
    partial upgrade does not fail.

    Version 3 bumps schema then rewrites legacy hard-cut thread titles in Python.
    Version 4 adds composer columns idempotently after legacy schema repair.
    Version 5 adds agents.is_shared idempotently after legacy schema repair.
    Version 6 adds published_experts idempotently after legacy schema repair.
    Version 7 applies OIDC SSO schema via migration SQL.
    Version 8 applies knowledge bases schema idempotently (tables may already
    exist from pre-renumber local upgrades that used an earlier 006).
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
    if version == 5:
        if _table_exists(db, "agents"):
            _ensure_column(db, "agents", "is_shared", "INTEGER NOT NULL DEFAULT 0")
            with db.connect() as conn:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_agents_shared "
                    "ON agents(is_shared) WHERE is_shared = 1"
                )
        with db.connect() as conn:
            conn.execute("UPDATE _schema_version SET version = ?", (version,))
        return
    if version == 6:
        _ensure_published_experts_table(db)
        _ensure_published_experts_indexes(db)
        with db.connect() as conn:
            conn.execute("UPDATE _schema_version SET version = ?", (version,))
        return
    if version == 8:
        _ensure_knowledge_bases_schema(db)
        with db.connect() as conn:
            conn.execute("UPDATE _schema_version SET version = ?", (version,))
        return
    if version == 9:
        if _table_exists(db, "knowledge_bases"):
            _ensure_column(db, "knowledge_bases", "icon_name", "TEXT NOT NULL DEFAULT ''")
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
