"""tests/unit/test_db_pool.py"""

from __future__ import annotations

import os
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
    }
    assert expected.issubset(names)


def test_run_migrations_idempotent(db: SqlitePool):
    run_migrations(db)
    with db.connect() as conn:
        v = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        cron_cols = {r["name"] for r in conn.execute("PRAGMA table_info(cron_jobs)").fetchall()}
    assert v == 1
    assert "login_failed_count" in cols
    assert "login_locked_until" in cols
    assert "preferences_json" in cols
    assert "task_type" in cron_cols


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
