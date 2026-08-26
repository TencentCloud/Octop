"""Apply numbered SQL migrations.

Each file is ``NNN_description.sql`` (SQLite) or ``NNN_description.pg.sql``
(PostgreSQL). Version is stored in ``_schema_version``.
"""

from __future__ import annotations

import json
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
        if db.dialect == "postgresql":
            rows = conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = ?",
                (table,),
            ).fetchall()
            names: set[str] = set()
            for row in rows:
                if isinstance(row, Mapping):
                    names.add(str(row["column_name"]))
                else:
                    names.add(str(row[0]))
            return names
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _table_exists(db: DatabasePool, table: str) -> bool:
    with db.connect() as conn:
        if db.dialect == "postgresql":
            row = conn.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = ?",
                (table,),
            ).fetchone()
        else:
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


_AGENT_PROFILE_COLUMNS = (
    "color",
    "icon_name",
    "icon_url",
    "skill_package_ids",
    "published_expert_id",
    "welcome_message",
)


def _drop_column(db: DatabasePool, table: str, column: str) -> None:
    if column not in _table_columns(db, table):
        return
    with db.connect() as conn:
        if db.dialect == "postgresql":
            conn.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
        else:
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")


def _ensure_agent_profile_columns(db: DatabasePool) -> None:
    if not _table_exists(db, "agents"):
        return
    for column in _AGENT_PROFILE_COLUMNS:
        _ensure_column(db, "agents", column, "TEXT")
    _collapse_legacy_agent_welcome_columns(db)


def _collapse_legacy_agent_welcome_columns(db: DatabasePool) -> None:
    """Fold welcome_message_zh/en into a single instance-owned welcome_message."""
    if not _table_exists(db, "agents"):
        return
    if db.dialect == "postgresql":
        with db.connect() as conn:
            conn.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS welcome_message TEXT")
    else:
        _ensure_column(db, "agents", "welcome_message", "TEXT")
    cols = _table_columns(db, "agents")
    has_zh = "welcome_message_zh" in cols
    has_en = "welcome_message_en" in cols
    if not has_zh and not has_en:
        return
    select_cols = ["agent_id", "welcome_message"]
    if has_zh:
        select_cols.append("welcome_message_zh")
    if has_en:
        select_cols.append("welcome_message_en")
    with db.transaction() as conn:
        rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM agents").fetchall()
        for row in rows:
            current = str(row["welcome_message"] or "").strip()
            if current:
                continue
            zh = str(row["welcome_message_zh"] or "").strip() if has_zh else ""
            en = str(row["welcome_message_en"] or "").strip() if has_en else ""
            picked = zh or en
            if not picked:
                continue
            conn.execute(
                "UPDATE agents SET welcome_message = ? WHERE agent_id = ?",
                (picked, row["agent_id"]),
            )
    _drop_column(db, "agents", "welcome_message_zh")
    _drop_column(db, "agents", "welcome_message_en")


def _backfill_agent_profile_from_config(db: DatabasePool) -> None:
    """Copy display metadata out of ``config_json`` into first-class columns."""
    if not _table_exists(db, "agents"):
        return
    cols = _table_columns(db, "agents")
    if "icon_name" not in cols:
        return
    from octop.infra.agents.profile import (  # noqa: PLC0415
        PROFILE_CONFIG_KEYS,
        extract_profile_from_config,
        parse_config_json,
        strip_profile_config,
    )

    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT agent_id, template_name, color, icon_name, icon_url, "
            "skill_package_ids, published_expert_id, welcome_message, "
            "config_json FROM agents"
        ).fetchall()
        for row in rows:
            cfg = parse_config_json(row["config_json"])
            if not cfg:
                continue
            profile = extract_profile_from_config(cfg)
            needs_strip = any(key in cfg for key in PROFILE_CONFIG_KEYS)
            updates: dict[str, object] = {}
            for column in (
                "color",
                "icon_name",
                "icon_url",
                "skill_package_ids",
                "published_expert_id",
                "welcome_message",
            ):
                if column not in profile:
                    continue
                current = row[column]
                if current is None or not str(current).strip():
                    updates[column] = profile[column]
            template = row["template_name"]
            if (template is None or not str(template).strip()) and profile.get("template_name"):
                updates["template_name"] = profile["template_name"]
            if needs_strip:
                updates["config_json"] = json.dumps(
                    strip_profile_config(cfg),
                    ensure_ascii=False,
                )
            if not updates:
                continue
            assignments = ", ".join(f"{column} = ?" for column in updates)
            params: list[object] = [*updates.values(), row["agent_id"]]
            conn.execute(
                f"UPDATE agents SET {assignments} WHERE agent_id = ?",
                params,
            )


def _integer_pk_sql(db: DatabasePool) -> str:
    if db.dialect == "postgresql":
        return "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
    return "INTEGER PRIMARY KEY AUTOINCREMENT"


def _skill_packages_identity_ready(db: DatabasePool) -> bool:
    return _table_exists(db, "skill_packages") and "skill_package_id" in _table_columns(
        db, "skill_packages"
    )


def _create_skill_packages_identity_table(db: DatabasePool) -> None:
    pk = _integer_pk_sql(db)
    with db.connect() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS skill_packages (
              id {pk},
              skill_package_id TEXT NOT NULL UNIQUE,
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
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_packages_name ON skill_packages(name)"
        )


def _rebuild_skill_packages_identity_schema(db: DatabasePool) -> None:
    """Give skill_packages an integer PK plus public ``skill_package_id``."""
    if _skill_packages_identity_ready(db):
        return
    if not _table_exists(db, "skill_packages"):
        _create_skill_packages_identity_table(db)
        return
    if "icon_name" not in _table_columns(db, "skill_packages"):
        _ensure_column(db, "skill_packages", "icon_name", "TEXT NOT NULL DEFAULT ''")
    if "icon_url" not in _table_columns(db, "skill_packages"):
        _ensure_column(db, "skill_packages", "icon_url", "TEXT NOT NULL DEFAULT ''")
    pk = _integer_pk_sql(db)
    with db.transaction() as conn:
        if db.dialect == "sqlite":
            conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("ALTER TABLE skill_packages RENAME TO skill_packages_legacy")
        conn.execute(
            f"""
            CREATE TABLE skill_packages (
              id {pk},
              skill_package_id TEXT NOT NULL UNIQUE,
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
        conn.execute(
            """
            INSERT INTO skill_packages(
              skill_package_id, name, description, created_by, skill_count,
              icon_name, icon_url, created_at, updated_at
            )
            SELECT id, name, description, created_by, skill_count,
              COALESCE(icon_name, ''), COALESCE(icon_url, ''), created_at, updated_at
            FROM skill_packages_legacy
            """
        )
        conn.execute("DROP TABLE skill_packages_legacy")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_packages_name ON skill_packages(name)"
        )
        if db.dialect == "sqlite":
            conn.execute("PRAGMA foreign_keys = ON")


def _ensure_skill_packages_schema(db: DatabasePool) -> None:
    """Create or rebuild skill_packages to the integer-PK identity schema."""
    _rebuild_skill_packages_identity_schema(db)


def _published_experts_identity_ready(db: DatabasePool) -> bool:
    return _table_exists(db, "published_experts") and "published_expert_id" in _table_columns(
        db, "published_experts"
    )


def _create_published_experts_identity_table(db: DatabasePool) -> None:
    pk = _integer_pk_sql(db)
    with db.connect() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS published_experts (
              id {pk},
              published_expert_id TEXT NOT NULL UNIQUE,
              slug TEXT NOT NULL,
              name TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              created_by TEXT NOT NULL,
              source_agent_id TEXT,
              icon_name TEXT NOT NULL DEFAULT '',
              color TEXT NOT NULL DEFAULT '',
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_published_experts_slug "
            "ON published_experts(slug)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_published_experts_created_by "
            "ON published_experts(created_by)"
        )


def _rebuild_published_experts_identity_schema(db: DatabasePool) -> None:
    """Give published_experts an integer PK plus public ``published_expert_id``."""
    if _published_experts_identity_ready(db):
        return
    if not _table_exists(db, "published_experts"):
        _create_published_experts_identity_table(db)
        return
    pk = _integer_pk_sql(db)
    with db.transaction() as conn:
        if db.dialect == "sqlite":
            conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("ALTER TABLE published_experts RENAME TO published_experts_legacy")
        conn.execute(
            f"""
            CREATE TABLE published_experts (
              id {pk},
              published_expert_id TEXT NOT NULL UNIQUE,
              slug TEXT NOT NULL,
              name TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              created_by TEXT NOT NULL,
              source_agent_id TEXT,
              icon_name TEXT NOT NULL DEFAULT '',
              color TEXT NOT NULL DEFAULT '',
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO published_experts(
              published_expert_id, slug, name, description, created_by,
              source_agent_id, icon_name, color, created_at, updated_at
            )
            SELECT id, slug, name, description, created_by,
              source_agent_id, COALESCE(icon_name, ''), COALESCE(color, ''),
              created_at, updated_at
            FROM published_experts_legacy
            """
        )
        conn.execute("DROP TABLE published_experts_legacy")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_published_experts_slug "
            "ON published_experts(slug)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_published_experts_created_by "
            "ON published_experts(created_by)"
        )
        if db.dialect == "sqlite":
            conn.execute("PRAGMA foreign_keys = ON")


def _ensure_published_experts_schema(db: DatabasePool) -> None:
    """Create or rebuild published_experts to the integer-PK identity schema."""
    _rebuild_published_experts_identity_schema(db)


def _relation_exists(db: DatabasePool, table: str, conn: Any | None = None) -> bool:
    def _run(cursor: Any) -> bool:
        if db.dialect == "postgresql":
            row = cursor.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = ?",
                (table,),
            ).fetchone()
        else:
            row = cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
        return row is not None

    if conn is not None:
        return _run(conn)
    with db.connect() as cursor:
        return _run(cursor)


def _relation_columns(db: DatabasePool, table: str) -> set[str]:
    with db.connect() as conn:
        if db.dialect == "postgresql":
            rows = conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = ?",
                (table,),
            ).fetchall()
            return {str(row["column_name"] if isinstance(row, Mapping) else row[0]) for row in rows}
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _knowledge_identity_ready(db: DatabasePool) -> bool:
    if not _relation_exists(db, "knowledge_bases"):
        return False
    cols = _relation_columns(db, "knowledge_bases")
    doc_cols = (
        _relation_columns(db, "knowledge_documents")
        if _relation_exists(db, "knowledge_documents")
        else set()
    )
    return "knowledge_base_id" in cols and "document_id" in doc_cols and "path" in doc_cols


def _create_knowledge_identity_tables(db: DatabasePool) -> None:
    pk = _integer_pk_sql(db)
    with db.connect() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS knowledge_bases (
              id {pk},
              knowledge_base_id TEXT NOT NULL UNIQUE,
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_bases_owner ON knowledge_bases(owner_user_id)"
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS knowledge_documents (
              id {pk},
              document_id TEXT NOT NULL UNIQUE,
              kb_id TEXT NOT NULL REFERENCES knowledge_bases(knowledge_base_id) ON DELETE CASCADE,
              path TEXT NOT NULL,
              filename TEXT NOT NULL,
              is_dir INTEGER NOT NULL DEFAULT 0,
              content_type TEXT NOT NULL,
              byte_size INTEGER NOT NULL,
              content_hash TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'pending',
              error_message TEXT NOT NULL DEFAULT '',
              chunk_count INTEGER NOT NULL DEFAULT 0,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL,
              UNIQUE(kb_id, path)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_documents_kb ON knowledge_documents(kb_id)"
        )


def _rebuild_knowledge_identity_schema(db: DatabasePool) -> None:
    """Give knowledge tables integer PKs + public string ids; add document folders."""
    if _knowledge_identity_ready(db):
        return
    if not _relation_exists(db, "knowledge_bases"):
        _create_knowledge_identity_tables(db)
        return
    pk = _integer_pk_sql(db)
    with db.transaction() as conn:
        if db.dialect == "sqlite":
            conn.execute("PRAGMA foreign_keys = OFF")
        if _relation_exists(db, "knowledge_base_members", conn):
            conn.execute("DROP TABLE knowledge_base_members")
        conn.execute("ALTER TABLE knowledge_bases RENAME TO knowledge_bases_legacy")
        if _relation_exists(db, "knowledge_documents", conn):
            conn.execute("ALTER TABLE knowledge_documents RENAME TO knowledge_documents_legacy")
        else:
            conn.execute(
                """
                CREATE TABLE knowledge_documents_legacy (
                  id TEXT PRIMARY KEY,
                  kb_id TEXT NOT NULL,
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
            f"""
            CREATE TABLE knowledge_bases (
              id {pk},
              knowledge_base_id TEXT NOT NULL UNIQUE,
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
        conn.execute(
            """
            INSERT INTO knowledge_bases(
              knowledge_base_id, owner_user_id, name, description, default_open,
              shared, icon_name, embedding_model, embedding_dim, doc_count,
              created_at, updated_at
            )
            SELECT id, owner_user_id, name, description, default_open,
              COALESCE(shared, 0), COALESCE(icon_name, ''), embedding_model,
              embedding_dim, doc_count, created_at, updated_at
            FROM knowledge_bases_legacy
            """
        )
        conn.execute(
            f"""
            CREATE TABLE knowledge_documents (
              id {pk},
              document_id TEXT NOT NULL UNIQUE,
              kb_id TEXT NOT NULL REFERENCES knowledge_bases(knowledge_base_id) ON DELETE CASCADE,
              path TEXT NOT NULL,
              filename TEXT NOT NULL,
              is_dir INTEGER NOT NULL DEFAULT 0,
              content_type TEXT NOT NULL,
              byte_size INTEGER NOT NULL,
              content_hash TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'pending',
              error_message TEXT NOT NULL DEFAULT '',
              chunk_count INTEGER NOT NULL DEFAULT 0,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL,
              UNIQUE(kb_id, path)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO knowledge_documents(
              document_id, kb_id, path, filename, is_dir, content_type, byte_size,
              content_hash, status, error_message, chunk_count, created_at, updated_at
            )
            SELECT id, kb_id, filename, filename, 0, content_type, byte_size,
              content_hash, status, error_message, chunk_count, created_at, updated_at
            FROM knowledge_documents_legacy
            """
        )
        conn.execute("DROP TABLE knowledge_documents_legacy")
        conn.execute("DROP TABLE knowledge_bases_legacy")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_bases_owner ON knowledge_bases(owner_user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_documents_kb ON knowledge_documents(kb_id)"
        )
        if db.dialect == "sqlite":
            conn.execute("PRAGMA foreign_keys = ON")


def _drop_knowledge_base_members(db: DatabasePool) -> None:
    if not _relation_exists(db, "knowledge_base_members"):
        return
    with db.connect() as conn:
        conn.execute("DROP TABLE knowledge_base_members")


def _ensure_knowledge_bases_schema(db: DatabasePool) -> None:
    """Create or rebuild knowledge tables to the integer-PK identity schema."""
    _rebuild_knowledge_identity_schema(db)
    _drop_knowledge_base_members(db)


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


def _ensure_usage_cache_schema(db: DatabasePool) -> None:
    """Backfill cache-aware usage columns for upgraded and repaired databases."""
    if not _table_exists(db, "usage_log"):
        return
    token_type = "BIGINT" if db.dialect == "postgresql" else "INTEGER"
    for column in (
        "uncached_input_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
    ):
        _ensure_column(
            db,
            "usage_log",
            column,
            f"{token_type} NOT NULL DEFAULT 0",
        )
    _ensure_column(db, "usage_log", "model_calls", "INTEGER NOT NULL DEFAULT 1")
    with db.connect() as conn:
        conn.execute(
            "UPDATE usage_log SET uncached_input_tokens = input_tokens "
            "WHERE uncached_input_tokens = 0 AND input_tokens > 0 "
            "AND cache_read_tokens = 0 AND cache_write_tokens = 0"
        )


def _ensure_user_invites_schema(db: DatabasePool) -> None:
    """Create ``user_invites`` when missing (clamp / repair paths)."""
    if _table_exists(db, "user_invites") or not _table_exists(db, "users"):
        return
    if db.dialect == "postgresql":
        with db.connect() as conn, conn.transaction():
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_invites (
                  id                BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                  code              TEXT NOT NULL UNIQUE,
                  created_by        BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  note              TEXT,
                  created_at        BIGINT NOT NULL,
                  expires_at        BIGINT NOT NULL,
                  used_at           BIGINT,
                  used_by_user_id   BIGINT REFERENCES users(id) ON DELETE SET NULL,
                  revoked_at        BIGINT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_invites_created_at "
                "ON user_invites(created_at DESC)"
            )
        return
    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_invites (
              id                INTEGER PRIMARY KEY AUTOINCREMENT,
              code              TEXT NOT NULL UNIQUE,
              created_by        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              note              TEXT,
              created_at        INTEGER NOT NULL,
              expires_at        INTEGER NOT NULL,
              used_at           INTEGER,
              used_by_user_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
              revoked_at        INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_user_invites_created_at
              ON user_invites(created_at DESC);
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
        _ensure_column(db, "threads", "artifacts", "TEXT NOT NULL DEFAULT '[]'")
    if _table_exists(db, "agents"):
        _ensure_column(db, "agents", "is_shared", "INTEGER NOT NULL DEFAULT 0")
        _ensure_agent_profile_columns(db)
        _backfill_agent_profile_from_config(db)
    _ensure_skill_packages_schema(db)
    _ensure_published_experts_schema(db)
    _ensure_usage_cache_schema(db)
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
        # v7 SQL rebuilds tables with RENAME; re-applying it would copy integer
        # ``id`` into public ``*_id`` columns. Use idempotent helpers instead.
        if max_version >= 7:
            _ensure_agent_profile_columns(db)
            _backfill_agent_profile_from_config(db)
            if _table_exists(db, "threads"):
                _ensure_column(db, "threads", "artifacts", "TEXT NOT NULL DEFAULT '[]'")
            _rebuild_knowledge_identity_schema(db)
            _drop_knowledge_base_members(db)
            _ensure_skill_packages_schema(db)
            _ensure_published_experts_schema(db)
            if max_version >= 8:
                _ensure_usage_cache_schema(db)
            if max_version >= 9:
                _ensure_user_invites_schema(db)
            with db.connect() as conn:
                conn.execute("UPDATE _schema_version SET version = %s", (max_version,))
            return
        path = next(path for version, path in _discover("postgresql") if version == max_version)
        sql = path.read_text(encoding="utf-8")
        with db.connect() as conn, conn.transaction():
            _apply_postgresql_migration(conn, sql)
            conn.execute("UPDATE _schema_version SET version = %s", (max_version,))
        return
    # SQLite: ensure helpers already ran via _repair_legacy_schema; also apply
    # the max migration's ensure path so clamping to a new max (e.g. 6) does not
    # skip ADD COLUMN for DBs that previously sat at version 7–9.
    if max_version >= 6 and _table_exists(db, "users"):
        _ensure_column(db, "users", "permissions", "TEXT NOT NULL DEFAULT '[]'")
    if max_version >= 7:
        _ensure_agent_profile_columns(db)
        _backfill_agent_profile_from_config(db)
        if _table_exists(db, "threads"):
            _ensure_column(db, "threads", "artifacts", "TEXT NOT NULL DEFAULT '[]'")
        _rebuild_knowledge_identity_schema(db)
        _drop_knowledge_base_members(db)
        _ensure_skill_packages_schema(db)
        _ensure_published_experts_schema(db)
    if max_version >= 8:
        _ensure_usage_cache_schema(db)
    if max_version >= 9:
        _ensure_user_invites_schema(db)
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
    Version 7 matches ``007_resource_identity_and_profile.sql``: profile
    columns, thread artifacts, integer PK + public string ids, document
    folders, drop ``knowledge_base_members``. SQLite uses these helpers
    (idempotent); PostgreSQL runs the ``.pg.sql`` file then the same helpers
    as a no-op safety net. ``config_json`` profile keys are backfilled in
    Python either way.
        Version 8 adds cache-aware usage buckets and model call counts.
        Version 9 adds one-time ``user_invites`` codes.
        Version 10 adds the dashboard thread-message projection when the legacy
        database actually contains conversation tables.
    """
    if version == 2:
        if _table_exists(db, "cron_jobs"):
            _ensure_column(
                db,
                "cron_jobs",
                "mcp_servers",
                "TEXT NOT NULL DEFAULT '[]'",
            )
        _ensure_skill_packages_schema(db)
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
        _ensure_published_experts_schema(db)
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
        _ensure_agent_profile_columns(db)
        _backfill_agent_profile_from_config(db)
        if _table_exists(db, "threads"):
            _ensure_column(db, "threads", "artifacts", "TEXT NOT NULL DEFAULT '[]'")
        _rebuild_knowledge_identity_schema(db)
        _drop_knowledge_base_members(db)
        _ensure_skill_packages_schema(db)
        _ensure_published_experts_schema(db)
        with db.connect() as conn:
            conn.execute("UPDATE _schema_version SET version = ?", (version,))
        return
    if version == 8:
        _ensure_usage_cache_schema(db)
        with db.connect() as conn:
            conn.execute("UPDATE _schema_version SET version = ?", (version,))
        return
    if version == 9:
        _ensure_user_invites_schema(db)
        with db.connect() as conn:
            conn.execute("UPDATE _schema_version SET version = ?", (version,))
        return
    if version == 10 and not _table_exists(db, "threads"):
        # Some very old/partial installs only contain ``users``. They still
        # need the version watermark to advance, but there is no history to
        # project and the migration's INSERT ... SELECT threads cannot run.
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
            if version == 7:
                _backfill_agent_profile_from_config(db)
                _rebuild_knowledge_identity_schema(db)
                _drop_knowledge_base_members(db)
                _collapse_legacy_agent_welcome_columns(db)
                _ensure_skill_packages_schema(db)
                _ensure_published_experts_schema(db)
        else:
            _apply_sqlite_migration(db, version, path)
    _reconcile_pre_squash_schema_version(db)
    _ensure_skill_packages_schema(db)
    _ensure_published_experts_schema(db)
    _ensure_usage_cache_schema(db)
    _ensure_user_invites_schema(db)
