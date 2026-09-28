"""Schema v19: project-management domain.

Covers the versioned path (fresh DB), the idempotent re-run path, and the
``_ensure_projects_schema`` repair path used when a database's recorded version
skipped 019.

Uses ``tmp_path`` throughout so the suite runs on Windows and POSIX alike.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.users import UserRepo

PROJECT_TABLES = (
    "projects",
    "project_members",
    "project_tasks",
    "project_comments",
    "node_mark_logs",
    "requirement_nodes",
    "project_rooms",
    "project_room_members",
    "project_artifacts",
    "timeline_events",
)


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def _table_names(db: SqlitePool) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row["name"]) for row in rows}


def _version(db: SqlitePool) -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT version FROM _schema_version").fetchone()
    return int(row["version"])


def _columns(db: SqlitePool, table: str) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def test_migration_019_is_the_applied_watermark(db: SqlitePool):
    assert _version(db) == 24


def test_migration_019_creates_all_project_tables(db: SqlitePool):
    names = _table_names(db)
    missing = sorted(set(PROJECT_TABLES) - names)
    assert missing == [], f"missing project tables: {missing}"


def test_migration_019_does_not_alter_threads(db: SqlitePool):
    """Project linkage resolves by reverse lookup, so threads must stay untouched."""
    columns = _columns(db, "threads")
    assert "project_id" not in columns
    # The v17 columns are still exactly what the previous migration left.
    assert {"conversation_mode", "pending_plan_path", "hitl_policy"} <= columns


def test_migration_019_is_idempotent(tmp_path: Path):
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    run_migrations(pool)  # must not raise (CREATE ... IF NOT EXISTS everywhere)
    assert _version(pool) == 24
    assert set(PROJECT_TABLES) <= _table_names(pool)


def test_ensure_projects_schema_repairs_missing_tables(db: SqlitePool):
    """A DB recorded at the latest version but missing the tables must be repaired
    on next run."""
    with db.transaction() as conn:
        for table in PROJECT_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
    assert not (set(PROJECT_TABLES) & _table_names(db))

    run_migrations(db)  # version already current -> only the unconditional helpers run

    assert set(PROJECT_TABLES) <= _table_names(db)
    assert _version(db) == 24


def test_projects_project_id_is_unique(db: SqlitePool):
    """Resource-table convention: integer PK + public string id, UNIQUE."""
    uid = UserRepo(db).create(username="owner", password_hash="h", role="user")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO projects (project_id, name, owner_user_id, memory_namespace,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("prj_1", "Demo", uid, "project_prj_1", 1, 1),
        )
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO projects (project_id, name, owner_user_id, memory_namespace,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("prj_1", "Duplicate", uid, "project_prj_1", 1, 1),
        )


def test_project_members_subject_is_unique_per_project(db: SqlitePool):
    uid = UserRepo(db).create(username="owner", password_hash="h", role="user")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO projects (project_id, name, owner_user_id, memory_namespace,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("prj_1", "Demo", uid, "project_prj_1", 1, 1),
        )
        conn.execute(
            "INSERT INTO project_members (project_id, subject_type, subject_id, user_id,"
            " role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("prj_1", "user", str(uid), uid, "owner", 1),
        )
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO project_members (project_id, subject_type, subject_id,"
            " user_id, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("prj_1", "user", str(uid), uid, "member", 1),
        )


def test_project_child_rows_cascade_from_project(db: SqlitePool):
    """Child tables reference projects(project_id) and cascade on delete."""
    uid = UserRepo(db).create(username="owner", password_hash="h", role="user")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO projects (project_id, name, owner_user_id, memory_namespace,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("prj_1", "Demo", uid, "project_prj_1", 1, 1),
        )
        conn.execute(
            "INSERT INTO project_tasks (task_id, project_id, title, created_by,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("task_1", "prj_1", "Task", uid, 1, 1),
        )
        conn.execute("DELETE FROM projects WHERE project_id = ?", ("prj_1",))
        remaining = conn.execute("SELECT COUNT(*) AS n FROM project_tasks").fetchone()
    assert int(remaining["n"]) == 0
