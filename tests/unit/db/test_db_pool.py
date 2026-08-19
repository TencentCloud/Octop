"""tests/unit/test_db_pool.py"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def test_db_pool_creates_file(tmp_path: Path):
    db_path = tmp_path / "octop.db"
    SqlitePool(db_path)
    assert db_path.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only mode bits")
def test_db_pool_file_is_0600(tmp_path: Path):
    db_path = tmp_path / "octop.db"
    SqlitePool(db_path)
    mode = db_path.stat().st_mode & 0o777
    assert mode == 0o600


def test_run_migrations_creates_tables(db: SqlitePool):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = {r["name"] for r in rows}
    expected = {
        "users",
        "agents",
        "providers",
        "channels",
        "cron_jobs",
        "sessions",
        "threads",
        "connectors",
        "connector_oauth_states",
        "secrets",
        "audit_log",
        "_schema_version",
        "storage_backends",
        "usage_log",
        "settings",
        "voice_providers",
        "proactive_care_config",
        "care_push_records",
        "skill_packages",
        "published_experts",
        "knowledge_bases",
        "knowledge_documents",
        "sso_providers",
        "sso_login_states",
    }
    assert expected.issubset(names)
    assert "knowledge_base_members" not in names


def test_run_migrations_idempotent(db: SqlitePool):
    run_migrations(db)
    with db.connect() as conn:
        v = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        cron_cols = {r["name"] for r in conn.execute("PRAGMA table_info(cron_jobs)").fetchall()}
        thread_cols = {r["name"] for r in conn.execute("PRAGMA table_info(threads)").fetchall()}
        agent_cols = {r["name"] for r in conn.execute("PRAGMA table_info(agents)").fetchall()}
        table_names = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        kb_cols = {r["name"] for r in conn.execute("PRAGMA table_info(knowledge_bases)").fetchall()}
        doc_cols = {
            r["name"] for r in conn.execute("PRAGMA table_info(knowledge_documents)").fetchall()
        }
    assert v == 7
    assert "login_failed_count" in cols
    assert "login_locked_until" in cols
    assert "preferences_json" in cols
    assert "permissions" in cols
    assert {"email", "sso_provider_id", "sso_subject"}.issubset(cols)
    assert "task_type" in cron_cols
    assert "mcp_servers" in cron_cols
    assert {"model_ref", "reasoning_mode", "reasoning_effort", "artifacts"}.issubset(thread_cols)
    assert {
        "color",
        "icon_name",
        "icon_url",
        "skill_package_ids",
        "published_expert_id",
        "welcome_message",
    }.issubset(agent_cols)
    assert "skill_packages" in table_names
    assert "knowledge_base_id" in kb_cols
    assert {"document_id", "path", "is_dir"}.issubset(doc_cols)


def test_repair_legacy_schema_ensures_columns(tmp_path: Path) -> None:
    """DBs missing columns must be repaired on boot even if schema version is ahead."""
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    with pool.connect() as conn:
        conn.executescript(
            (
                Path(__file__).resolve().parents[3]
                / "src/octop/infra/db/migrations/001_initial.sql"
            ).read_text()
        )
        # Simulate a schema version ahead of what the columns reflect
        conn.execute("UPDATE _schema_version SET version = 2")
    run_migrations(pool)
    with pool.connect() as conn:
        cron_cols = {r["name"] for r in conn.execute("PRAGMA table_info(cron_jobs)").fetchall()}
    assert "task_type" in cron_cols


def test_migration_002_idempotent_when_column_already_present(tmp_path: Path) -> None:
    """Partial upgrade: mcp_servers exists but version still 1 must not fail."""
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    with pool.connect() as conn:
        conn.executescript(
            (
                Path(__file__).resolve().parents[3]
                / "src/octop/infra/db/migrations/001_initial.sql"
            ).read_text()
        )
        conn.execute("ALTER TABLE cron_jobs ADD COLUMN mcp_servers TEXT NOT NULL DEFAULT '[]'")
    run_migrations(pool)
    with pool.connect() as conn:
        v = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        cron_cols = {r["name"] for r in conn.execute("PRAGMA table_info(cron_jobs)").fetchall()}
    assert v == 7
    assert "mcp_servers" in cron_cols
    assert "skill_packages" in {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def test_migration_005_preserves_populated_users_and_constraints(tmp_path: Path) -> None:
    """A populated v4 DB keeps users and their foreign-key references at v5."""
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    initial_migration = (
        Path(__file__).resolve().parents[3] / "src/octop/infra/db/migrations/001_initial.sql"
    )
    with pool.connect() as conn:
        conn.executescript(initial_migration.read_text())
        conn.execute("UPDATE _schema_version SET version = 4")
        conn.execute(
            """
            INSERT INTO users(
              id, username, password_hash, role, display_name, disabled, locale,
              created_at, login_failed_count, login_locked_until, preferences_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (101, "legacy-user", "legacy-hash", "admin", "Legacy User", 1, "en", 10, 2, 20, "{}"),
        )
        conn.execute(
            """
            INSERT INTO agents(agent_id, user_id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("legacy-agent", 101, "Legacy Agent", 10, 20),
        )

    run_migrations(pool)

    with pool.connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (101,)).fetchone()
        agent = conn.execute(
            "SELECT agent_id, user_id, name FROM agents WHERE agent_id = ?",
            ("legacy-agent",),
        ).fetchone()
        assert user is not None
        assert dict(user) == {
            "id": 101,
            "username": "legacy-user",
            "password_hash": "legacy-hash",
            "role": "admin",
            "display_name": "Legacy User",
            "disabled": 1,
            "locale": "en",
            "created_at": 10,
            "login_failed_count": 2,
            "login_locked_until": 20,
            "preferences_json": "{}",
            "email": None,
            "sso_provider_id": None,
            "sso_subject": None,
            "permissions": "[]",
        }
        assert dict(agent) == {
            "agent_id": "legacy-agent",
            "user_id": 101,
            "name": "Legacy Agent",
        }
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        user_indexes = {
            row["name"]: row["partial"] for row in conn.execute("PRAGMA index_list(users)")
        }
        assert user_indexes["idx_users_email"] == 1
        assert user_indexes["idx_users_sso"] == 1
        user_foreign_keys = conn.execute("PRAGMA foreign_key_list(users)").fetchall()
        assert any(
            row["from"] == "sso_provider_id" and row["table"] == "sso_providers"
            for row in user_foreign_keys
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO agents(agent_id, user_id, name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("invalid-agent", 999, "Invalid Agent", 10, 20),
            )

        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at, email) VALUES (?, ?, ?, ?, ?)",
            ("passwordless", None, "user", 30, "person@example.com"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users(username, password_hash, role, created_at, email) VALUES (?, ?, ?, ?, ?)",
                ("duplicate-email", None, "user", 30, "person@example.com"),
            )

        conn.execute(
            """
            INSERT INTO sso_providers(
              id, enabled, display_name, issuer, client_id, scopes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, 1, "SSO", "https://issuer.example", "octop-client", "openid", 30, 30),
        )
        conn.execute(
            """
            INSERT INTO users(username, password_hash, role, created_at, sso_provider_id, sso_subject)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("sso-user", None, "user", 30, 1, "subject-1"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO users(username, password_hash, role, created_at, sso_provider_id, sso_subject)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("duplicate-sso", None, "user", 30, 1, "subject-1"),
            )


def test_stuck_version_6_without_permissions_column_is_repaired(tmp_path: Path) -> None:
    """Pre-squash version clamp can leave schema at 6 without users.permissions."""
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    with pool.connect() as conn:
        conn.executescript(
            (
                Path(__file__).resolve().parents[3]
                / "src/octop/infra/db/migrations/001_initial.sql"
            ).read_text()
        )
        conn.execute("UPDATE _schema_version SET version = 6")
    run_migrations(pool)
    with pool.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        version = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
    assert version == 7
    assert "permissions" in cols


def test_ahead_of_max_schema_version_clamps_to_v7(tmp_path: Path) -> None:
    """A local DB that recorded v8 (folded into unreleased v7) clamps on boot."""
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    with pool.connect() as conn:
        conn.executescript(
            (
                Path(__file__).resolve().parents[3]
                / "src/octop/infra/db/migrations/001_initial.sql"
            ).read_text()
        )
        conn.execute("UPDATE _schema_version SET version = 8")
    run_migrations(pool)
    with pool.connect() as conn:
        version = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        pkg_cols = {r["name"] for r in conn.execute("PRAGMA table_info(skill_packages)").fetchall()}
        pub_cols = {
            r["name"] for r in conn.execute("PRAGMA table_info(published_experts)").fetchall()
        }
    assert version == 7
    assert "skill_package_id" in pkg_cols
    assert "published_expert_id" in pub_cols


def test_foreign_keys_enabled(db: SqlitePool):
    with db.connect() as conn:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1


def test_pre_squash_schema_version_clamped_and_knowledge_tables_filled(
    tmp_path: Path,
) -> None:
    """Develop DBs that applied split 005–009 must clamp to consolidated v5."""
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    with pool.connect() as conn:
        conn.executescript(
            (
                Path(__file__).resolve().parents[3]
                / "src/octop/infra/db/migrations/001_initial.sql"
            ).read_text()
        )
        # Simulate a develop DB whose recorded version is ahead of the
        # consolidated max (v7), so reconcile clamps and repairs knowledge tables.
        conn.execute("UPDATE _schema_version SET version = 12")
        conn.execute("ALTER TABLE agents ADD COLUMN is_shared INTEGER NOT NULL DEFAULT 0")

    run_migrations(pool)

    with pool.connect() as conn:
        version = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    assert version == 7
    assert "permissions" in user_cols
    assert {
        "published_experts",
        "sso_providers",
        "sso_login_states",
        "knowledge_bases",
        "knowledge_documents",
    }.issubset(tables)
    kb_cols = {r["name"] for r in conn.execute("PRAGMA table_info(knowledge_bases)").fetchall()}
    pkg_cols = {r["name"] for r in conn.execute("PRAGMA table_info(skill_packages)").fetchall()}
    pub_cols = {r["name"] for r in conn.execute("PRAGMA table_info(published_experts)").fetchall()}
    assert "knowledge_base_id" in kb_cols
    assert "skill_package_id" in pkg_cols
    assert "published_expert_id" in pub_cols


def test_transaction_rolls_back_on_exception(db: SqlitePool):
    with pytest.raises(RuntimeError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, 0)",
            ("a", "h", "user"),
        )
        raise RuntimeError("boom")
    with db.connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert n == 0


def test_v7_sql_files_declare_identity_rebuild() -> None:
    """The numbered v7 pair must contain the table rebuild, not only ADD COLUMN."""
    root = Path(__file__).resolve().parents[3] / "src/octop/infra/db/migrations"
    sqlite_sql = (root / "007_resource_identity_and_profile.sql").read_text(encoding="utf-8")
    pg_sql = (root / "007_resource_identity_and_profile.pg.sql").read_text(encoding="utf-8")
    for sql in (sqlite_sql, pg_sql):
        for token in (
            "knowledge_base_id",
            "document_id",
            "skill_package_id",
            "published_expert_id",
            "ALTER TABLE knowledge_bases RENAME",
            "ALTER TABLE skill_packages RENAME",
            "ALTER TABLE published_experts RENAME",
            "DROP TABLE IF EXISTS knowledge_base_members",
            "ADD COLUMN",
            "welcome_message",
            "artifacts",
        ):
            assert token in sql


def test_v7_sqlite_sql_upgrades_legacy_text_pks(tmp_path: Path) -> None:
    """A clean v6-shaped DB can execute 007.sql without going through Python helpers."""
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    migrations = Path(__file__).resolve().parents[3] / "src/octop/infra/db/migrations"
    with pool.connect() as conn:
        conn.executescript((migrations / "001_initial.sql").read_text(encoding="utf-8"))
        conn.executescript(
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
            );
            CREATE TABLE published_experts (
              id TEXT PRIMARY KEY,
              slug TEXT NOT NULL,
              name TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              created_by TEXT NOT NULL,
              source_agent_id TEXT,
              icon_name TEXT NOT NULL DEFAULT '',
              color TEXT NOT NULL DEFAULT '',
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            );
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
              updated_at INTEGER NOT NULL
            );
            CREATE TABLE knowledge_base_members (
              kb_id TEXT NOT NULL,
              user_id INTEGER NOT NULL,
              role TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              PRIMARY KEY (kb_id, user_id)
            );
            CREATE TABLE knowledge_documents (
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
            );
            """
        )
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, 1)",
            ("owner", "h", "user"),
        )
        user_id = conn.execute("SELECT id FROM users WHERE username = 'owner'").fetchone()[0]
        conn.execute(
            "INSERT INTO skill_packages(id, name, created_by, created_at, updated_at) "
            "VALUES ('pkg1', 'Pack', 'owner', '1', '1')"
        )
        conn.execute(
            "INSERT INTO published_experts(id, slug, name, created_by, created_at, updated_at) "
            "VALUES ('pub1', 'slug', 'Expert', 'owner', 1, 1)"
        )
        conn.execute(
            "INSERT INTO knowledge_bases("
            "id, owner_user_id, name, embedding_model, embedding_dim, "
            "doc_count, created_at, updated_at) VALUES (?, ?, 'Docs', '', 0, 1, 1, 1)",
            ("kb1", user_id),
        )
        conn.execute(
            "INSERT INTO knowledge_base_members(kb_id, user_id, role, created_at) "
            "VALUES ('kb1', ?, 'owner', 1)",
            (user_id,),
        )
        conn.execute(
            "INSERT INTO knowledge_documents("
            "id, kb_id, filename, content_type, byte_size, created_at, updated_at) "
            "VALUES ('doc1', 'kb1', 'a.md', 'text/markdown', 1, 1, 1)"
        )
        conn.executescript((migrations / "007_resource_identity_and_profile.sql").read_text())

    with pool.connect() as conn:
        version = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        pkg = conn.execute("SELECT * FROM skill_packages").fetchone()
        pub = conn.execute("SELECT * FROM published_experts").fetchone()
        kb = conn.execute("SELECT * FROM knowledge_bases").fetchone()
        doc = conn.execute("SELECT * FROM knowledge_documents").fetchone()
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        agent_cols = {r["name"] for r in conn.execute("PRAGMA table_info(agents)").fetchall()}
        thread_cols = {r["name"] for r in conn.execute("PRAGMA table_info(threads)").fetchall()}
    assert version == 7
    assert "knowledge_base_members" not in tables
    assert "welcome_message" in agent_cols
    assert "artifacts" in thread_cols
    assert pkg["skill_package_id"] == "pkg1"
    assert pub["published_expert_id"] == "pub1"
    assert kb["knowledge_base_id"] == "kb1"
    assert doc["document_id"] == "doc1"
    assert doc["path"] == "a.md"
    assert doc["filename"] == "a.md"
