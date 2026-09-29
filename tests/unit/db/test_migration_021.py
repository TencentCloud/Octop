"""Schema v21: project configuration (connectors, skills, instruction, cron owner).

Covers the versioned path (fresh DB), the idempotent re-run path, the two new
tables with their constraints and cascades, the two new columns, the three new
indexes, and the ``7 DDL items`` budget frozen by ``PLAN.md §10.1``.

Uses ``tmp_path`` throughout so the suite runs on Windows and POSIX alike.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.users import UserRepo

SQLITE_FILE = "021_project_config.sql"
PG_FILE = "021_project_config.pg.sql"
NEW_TABLES = ("project_connectors", "project_skills")
NEW_INDEXES = (
    "idx_project_connectors_project",
    "idx_project_skills_project",
    "idx_cron_jobs_project",
)


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def _migrations_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "src/octop/infra/db/migrations"


def _table_names(db: SqlitePool) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row["name"]) for row in rows}


def _index_names(db: SqlitePool) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    return {str(row["name"]) for row in rows}


def _columns(db: SqlitePool, table: str) -> dict[str, sqlite3.Row]:
    with db.connect() as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]): row for row in rows}


def _version(db: SqlitePool) -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT version FROM _schema_version").fetchone()
    return int(row["version"])


# ── the watermark ────────────────────────────────────────────────────────────


def test_migration_021_is_the_applied_watermark(db: SqlitePool):
    assert _version(db) == 25


def test_migration_021_is_idempotent(tmp_path: Path):
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    run_migrations(pool)  # must not raise; every DDL item is IF NOT EXISTS guarded
    assert _version(pool) == 25
    assert set(NEW_TABLES) <= _table_names(pool)


# ── tables, columns, indexes ─────────────────────────────────────────────────


def test_migration_021_creates_the_two_declaration_tables(db: SqlitePool):
    missing = sorted(set(NEW_TABLES) - _table_names(db))
    assert missing == [], f"missing declaration tables: {missing}"


def test_migration_021_has_no_instance_id_or_credentials(db: SqlitePool):
    """R17: a project connector declaration stores the ``kind`` and nothing else."""
    assert set(_columns(db, "project_connectors")) == {
        "id",
        "project_id",
        "kind",
        "created_by",
        "created_at",
    }


def test_migration_021_adds_projects_instruction(db: SqlitePool):
    column = _columns(db, "projects")["instruction"]
    assert "TEXT" in str(column["type"]).upper()
    assert column["notnull"] == 1
    assert column["dflt_value"] == "''"


def test_migration_021_adds_cron_jobs_project_id(db: SqlitePool):
    column = _columns(db, "cron_jobs")["project_id"]
    assert "TEXT" in str(column["type"]).upper()
    assert column["notnull"] == 0  # NULL = personal job, not project-owned
    assert column["dflt_value"] is None


def test_migration_021_creates_the_three_indexes(db: SqlitePool):
    missing = sorted(set(NEW_INDEXES) - _index_names(db))
    assert missing == [], f"missing indexes: {missing}"


# ── constraints and cascades ─────────────────────────────────────────────────


def _seed_project(db: SqlitePool) -> int:
    uid = UserRepo(db).create(username="owner", password_hash="h", role="user")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO projects (project_id, name, owner_user_id, memory_namespace,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("prj_1", "Demo", uid, "project_prj_1", 1, 1),
        )
    return uid


def test_migration_021_connector_kind_is_unique_per_project(db: SqlitePool):
    uid = _seed_project(db)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO project_connectors (project_id, kind, created_by, created_at)"
            " VALUES (?, ?, ?, ?)",
            ("prj_1", "notion", uid, 1),
        )
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO project_connectors (project_id, kind, created_by, created_at)"
            " VALUES (?, ?, ?, ?)",
            ("prj_1", "notion", uid, 2),
        )


def test_migration_021_skill_slug_is_unique_per_agent_per_project(db: SqlitePool):
    uid = _seed_project(db)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO project_skills (project_id, agent_id, skill_slug, created_by,"
            " created_at) VALUES (?, ?, ?, ?, ?)",
            ("prj_1", "ag-a", "report", uid, 1),
        )
        # The same slug under another agent is a different skill — allowed.
        conn.execute(
            "INSERT INTO project_skills (project_id, agent_id, skill_slug, created_by,"
            " created_at) VALUES (?, ?, ?, ?, ?)",
            ("prj_1", "ag-b", "report", uid, 1),
        )
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO project_skills (project_id, agent_id, skill_slug, created_by,"
            " created_at) VALUES (?, ?, ?, ?, ?)",
            ("prj_1", "ag-a", "report", uid, 2),
        )


def test_migration_021_declarations_cascade_from_the_project(db: SqlitePool):
    uid = _seed_project(db)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO project_connectors (project_id, kind, created_by, created_at)"
            " VALUES (?, ?, ?, ?)",
            ("prj_1", "notion", uid, 1),
        )
        conn.execute(
            "INSERT INTO project_skills (project_id, agent_id, skill_slug, created_by,"
            " created_at) VALUES (?, ?, ?, ?, ?)",
            ("prj_1", "ag-a", "report", uid, 1),
        )
        conn.execute("DELETE FROM projects WHERE project_id = ?", ("prj_1",))
        connectors = conn.execute("SELECT COUNT(*) AS n FROM project_connectors").fetchone()["n"]
        skills = conn.execute("SELECT COUNT(*) AS n FROM project_skills").fetchone()["n"]
    assert (int(connectors), int(skills)) == (0, 0)


# ── the 7-item DDL budget (PLAN.md §10.1) ────────────────────────────────────


def _ddl_items(text: str) -> list[str]:
    """``CREATE TABLE`` / ``CREATE INDEX`` / ``ALTER TABLE`` statements, in order."""
    return re.findall(
        r"^(?:CREATE TABLE IF NOT EXISTS|CREATE INDEX IF NOT EXISTS|ALTER TABLE)\s+([a-z_]+)",
        text,
        re.M,
    )


def test_migration_021_has_exactly_seven_ddl_items():
    text = (_migrations_dir() / SQLITE_FILE).read_text(encoding="utf-8")
    items = _ddl_items(text)
    assert len(items) == 7, items
    assert items == [
        "project_connectors",
        "idx_project_connectors_project",
        "project_skills",
        "idx_project_skills_project",
        "projects",
        "cron_jobs",
        "idx_cron_jobs_project",
    ]
    assert "UPDATE _schema_version SET version = 21;" in text


def test_migration_021_pg_twin_matches_the_sqlite_ddl():
    sqlite_text = (_migrations_dir() / SQLITE_FILE).read_text(encoding="utf-8")
    pg_text = (_migrations_dir() / PG_FILE).read_text(encoding="utf-8")
    assert _ddl_items(pg_text) == _ddl_items(sqlite_text)
    assert "UPDATE _schema_version SET version = 21;" in pg_text
    assert "ADD COLUMN IF NOT EXISTS" in pg_text
