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


def _ensure_sso_oidc_schema(db: DatabasePool) -> None:
    """Apply OIDC SSO tables and nullable password_hash (SQLite users rebuild)."""
    if _table_exists(db, "sso_providers"):
        return
    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sso_providers (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              enabled INTEGER NOT NULL DEFAULT 0,
              display_name TEXT NOT NULL DEFAULT '',
              issuer TEXT NOT NULL DEFAULT '',
              client_id TEXT NOT NULL DEFAULT '',
              client_secret_enc BLOB,
              scopes TEXT NOT NULL DEFAULT 'openid profile email',
              dashboard_origin TEXT,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sso_login_states (
              state TEXT PRIMARY KEY,
              provider_id INTEGER NOT NULL REFERENCES sso_providers(id) ON DELETE CASCADE,
              nonce TEXT NOT NULL,
              code_verifier TEXT NOT NULL,
              redirect_after TEXT NOT NULL DEFAULT '/chat',
              login_code TEXT,
              user_id INTEGER,
              expires_at INTEGER NOT NULL,
              consumed_at INTEGER,
              created_at INTEGER NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_sso_login_states_login_code
              ON sso_login_states(login_code) WHERE login_code IS NOT NULL;

            PRAGMA foreign_keys = OFF;

            CREATE TABLE users_new (
              id                  INTEGER PRIMARY KEY AUTOINCREMENT,
              username            TEXT NOT NULL,
              password_hash       TEXT,
              role                TEXT NOT NULL,
              display_name        TEXT,
              disabled            INTEGER NOT NULL DEFAULT 0,
              locale              TEXT NOT NULL DEFAULT 'zh',
              created_at          INTEGER NOT NULL,
              login_failed_count  INTEGER NOT NULL DEFAULT 0,
              login_locked_until  INTEGER NOT NULL DEFAULT 0,
              preferences_json    TEXT NOT NULL DEFAULT '{}',
              email               TEXT,
              sso_provider_id     INTEGER REFERENCES sso_providers(id),
              sso_subject         TEXT,
              permissions         TEXT NOT NULL DEFAULT '[]'
            );

            INSERT INTO users_new (
              id,
              username,
              password_hash,
              role,
              display_name,
              disabled,
              locale,
              created_at,
              login_failed_count,
              login_locked_until,
              preferences_json,
              permissions
            )
            SELECT
              id,
              username,
              password_hash,
              role,
              display_name,
              disabled,
              locale,
              created_at,
              login_failed_count,
              login_locked_until,
              preferences_json,
              '[]'
            FROM users;

            DROP TABLE users;
            ALTER TABLE users_new RENAME TO users;

            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
              ON users(email) WHERE email IS NOT NULL AND email != '';
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_sso
              ON users(sso_provider_id, sso_subject)
              WHERE sso_provider_id IS NOT NULL AND sso_subject IS NOT NULL;

            PRAGMA foreign_keys = ON;
            """
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
        # Pre-squash DBs may already report version ≥6; reconcile can clamp to 6
        # without applying 006_user_permissions.sql — ensure the column here.
        _ensure_column(db, "users", "permissions", "TEXT NOT NULL DEFAULT '[]'")
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
    _ensure_column(db, "published_experts", "allow_skill_details", "INTEGER NOT NULL DEFAULT 1")
    # Cover pre-squash develop DBs that already recorded version ≥5 but only
    # applied a subset of the former 005–009 files (or the old thin 005).
    # Require ``users`` first — SSO rebuild and knowledge FKs need it, and a
    # brand-new DB has not applied 001 yet when repair runs.
    if _table_exists(db, "users"):
        _ensure_sso_oidc_schema(db)
        _ensure_knowledge_bases_schema(db)
        # SSO rebuild recreates ``users``; ensure permissions after that path.
        _ensure_column(db, "users", "permissions", "TEXT NOT NULL DEFAULT '[]'")


def _max_discovered_version(dialect: str) -> int:
    versions = [version for version, _ in _discover(dialect)]
    return max(versions) if versions else 0


def _reconcile_pre_squash_schema_version(db: DatabasePool) -> None:
    """Clamp develop DBs that applied split 005–009 down to the consolidated max.

    Before squash, local/develop installs could sit at schema versions 6–9.
    After those files are merged into a single 005, leaving version > max would
    permanently skip future migrations (e.g. a new 006).
    """
    current = _current_version(db)
    max_version = _max_discovered_version(db.dialect)
    if max_version <= 0 or current <= max_version:
        return
    if db.dialect == "postgresql":
        path = next(path for version, path in _discover("postgresql") if version == max_version)
        sql = path.read_text(encoding="utf-8")
        with db.connect() as conn, conn.transaction():
            _apply_postgresql_migration(conn, sql)
            conn.execute("UPDATE _schema_version SET version = %s", (max_version,))
        return
    # SQLite: ensure helpers already ran via _repair_legacy_schema; also apply
    # the max migration's ensure path so clamping to a new max (e.g. 6) does not
    # skip ADD COLUMN for DBs that previously sat at version 7–9.
    if max_version == 6 and _table_exists(db, "users"):
        _ensure_column(db, "users", "permissions", "TEXT NOT NULL DEFAULT '[]'")
    with db.connect() as conn:
        conn.execute("UPDATE _schema_version SET version = ?", (max_version,))


def _apply_postgresql_migration(conn: Any, sql: str) -> None:
    for stmt in _split_pg_sql(sql):
        conn.execute(stmt)


def _apply_sqlite_migration(db: DatabasePool, version: int, path: Path) -> None:
    """Apply one SQLite migration.

    Version 2 uses ``_ensure_column`` / table helpers so re-running after a
    partial upgrade does not fail.

    Version 3 bumps schema then rewrites legacy hard-cut thread titles in Python.
    Version 4 adds composer columns idempotently after legacy schema repair.
    Version 5 adds shared experts, published templates, OIDC SSO, and knowledge
    bases idempotently after legacy schema repair.
    Version 6 adds ``users.permissions`` idempotently (also covered by
    ``_repair_legacy_schema`` for DBs whose version was clamped past 006).
    Version 7 adds ``published_experts.allow_skill_details`` idempotently
    (``_repair_legacy_schema`` may have added it before 007 runs).
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
        _ensure_published_experts_table(db)
        _ensure_published_experts_indexes(db)
        _ensure_sso_oidc_schema(db)
        _ensure_knowledge_bases_schema(db)
        with db.connect() as conn:
            conn.execute("UPDATE _schema_version SET version = ?", (version,))
        return
    if version == 6:
        if _table_exists(db, "users"):
            _ensure_column(db, "users", "permissions", "TEXT NOT NULL DEFAULT '[]'")
        with db.connect() as conn:
            conn.execute("UPDATE _schema_version SET version = ?", (version,))
        return
    if version == 7:
        if _table_exists(db, "published_experts"):
            _ensure_column(
                db,
                "published_experts",
                "allow_skill_details",
                "INTEGER NOT NULL DEFAULT 1",
            )
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
    _reconcile_pre_squash_schema_version(db)
