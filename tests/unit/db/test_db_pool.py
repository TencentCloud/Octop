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
        "knowledge_base_members",
        "knowledge_documents",
        "sso_providers",
        "sso_login_states",
    }
    assert expected.issubset(names)


def test_run_migrations_idempotent(db: SqlitePool):
    run_migrations(db)
    with db.connect() as conn:
        v = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        cron_cols = {r["name"] for r in conn.execute("PRAGMA table_info(cron_jobs)").fetchall()}
        thread_cols = {r["name"] for r in conn.execute("PRAGMA table_info(threads)").fetchall()}
    assert v == 9
    assert "login_failed_count" in cols
    assert "login_locked_until" in cols
    assert "preferences_json" in cols
    assert {"email", "sso_provider_id", "sso_subject"}.issubset(cols)
    assert "task_type" in cron_cols
    assert "mcp_servers" in cron_cols
    assert {"model_ref", "reasoning_mode", "reasoning_effort"}.issubset(thread_cols)
    assert "skill_packages" in {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


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
    assert v == 9
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


def test_foreign_keys_enabled(db: SqlitePool):
    with db.connect() as conn:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1


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
