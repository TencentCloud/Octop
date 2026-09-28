"""Schema v20: project task metadata (tags, custom fields, dates, attachments).

Covers the versioned path (fresh DB), the idempotent re-run path, the four new
tables, the three new columns, and the DDL budget: ``PLAN.md §12.1``'s nine items
plus the two custom-field indexes ``§6.1`` freezes (11 statements; SPEC S-9
forbids anything beyond them, in particular a ``default`` column).

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

SQLITE_FILE = "020_project_task_metadata.sql"
PG_FILE = "020_project_task_metadata.pg.sql"
NEW_TABLES = (
    "project_tags",
    "project_task_tags",
    "project_custom_fields",
    "project_task_field_values",
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


def _index_names(db: SqlitePool, table: str) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
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


def test_migration_020_is_the_applied_watermark(db: SqlitePool):
    assert _version(db) == 22


def test_migration_020_is_idempotent(tmp_path: Path):
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    run_migrations(pool)  # must not raise; every DDL item is IF NOT EXISTS guarded
    assert _version(pool) == 22
    assert set(NEW_TABLES) <= _table_names(pool)


# ── tables and columns ───────────────────────────────────────────────────────


def test_migration_020_creates_the_four_metadata_tables(db: SqlitePool):
    missing = sorted(set(NEW_TABLES) - _table_names(db))
    assert missing == [], f"missing metadata tables: {missing}"


def test_migration_020_adds_task_start_at(db: SqlitePool):
    column = _columns(db, "project_tasks")["start_at"]
    assert "INTEGER" in str(column["type"]).upper()
    assert column["notnull"] == 0  # NULL = not scheduled yet
    assert column["dflt_value"] is None


def test_migration_020_adds_artifact_size_and_mime(db: SqlitePool):
    columns = _columns(db, "project_artifacts")
    assert "INTEGER" in str(columns["size"]["type"]).upper()
    assert columns["size"]["dflt_value"] == "0"
    assert "TEXT" in str(columns["mime"]["type"]).upper()
    assert columns["mime"]["dflt_value"] == "''"


def test_migration_020_creates_the_tag_indexes(db: SqlitePool):
    assert "idx_project_tags_project" in _index_names(db, "project_tags")
    assert "idx_project_task_tags_tag" in _index_names(db, "project_task_tags")


# ── constraints and cascades ─────────────────────────────────────────────────


def _seed_project(db: SqlitePool) -> int:
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
    return uid


def test_migration_020_tag_name_is_unique_per_project(db: SqlitePool):
    uid = _seed_project(db)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO project_tags (tag_id, project_id, name, created_by,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("tag_1", "prj_1", "urgent", uid, 1, 1),
        )
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO project_tags (tag_id, project_id, name, created_by,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("tag_2", "prj_1", "urgent", uid, 1, 1),
        )


def test_migration_020_task_tag_pair_is_unique(db: SqlitePool):
    uid = _seed_project(db)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO project_tags (tag_id, project_id, name, created_by,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("tag_1", "prj_1", "urgent", uid, 1, 1),
        )
        conn.execute(
            "INSERT INTO project_task_tags (task_id, tag_id, created_at) VALUES (?, ?, ?)",
            ("task_1", "tag_1", 1),
        )
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO project_task_tags (task_id, tag_id, created_at) VALUES (?, ?, ?)",
            ("task_1", "tag_1", 2),
        )


def test_migration_020_child_rows_cascade(db: SqlitePool):
    """Deleting the project takes its tags; deleting a task takes its links."""
    uid = _seed_project(db)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO project_tags (tag_id, project_id, name, created_by,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("tag_1", "prj_1", "urgent", uid, 1, 1),
        )
        conn.execute(
            "INSERT INTO project_task_tags (task_id, tag_id, created_at) VALUES (?, ?, ?)",
            ("task_1", "tag_1", 1),
        )
        conn.execute(
            "INSERT INTO project_custom_fields (field_id, project_id, key, label, type,"
            " created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("fld_1", "prj_1", "risk", "Risk", "text", uid, 1, 1),
        )
        conn.execute(
            "INSERT INTO project_task_field_values (task_id, field_id, value, updated_at)"
            " VALUES (?, ?, ?, ?)",
            ("task_1", "fld_1", "high", 1),
        )
        conn.execute("DELETE FROM project_tasks WHERE task_id = ?", ("task_1",))
        links = conn.execute("SELECT COUNT(*) AS n FROM project_task_tags").fetchone()["n"]
        values = conn.execute("SELECT COUNT(*) AS n FROM project_task_field_values").fetchone()["n"]
        conn.execute("DELETE FROM projects WHERE project_id = ?", ("prj_1",))
        tags = conn.execute("SELECT COUNT(*) AS n FROM project_tags").fetchone()["n"]
        fields = conn.execute("SELECT COUNT(*) AS n FROM project_custom_fields").fetchone()["n"]
    assert (int(links), int(values), int(tags), int(fields)) == (0, 0, 0, 0)


# ── the 11-item DDL budget (PLAN.md §12.1 + §6.1 indexes) ────────────────────


def _ddl_items(text: str) -> list[str]:
    """``CREATE TABLE`` / ``CREATE INDEX`` / ``ALTER TABLE`` statements, in order."""
    return re.findall(
        r"^(?:CREATE TABLE IF NOT EXISTS|CREATE INDEX IF NOT EXISTS|ALTER TABLE)\s+([a-z_]+)",
        text,
        re.M,
    )


def test_migration_020_has_exactly_eleven_ddl_items():
    """§12.1's nine items plus the two custom-field indexes §6.1 freezes."""
    text = (_migrations_dir() / SQLITE_FILE).read_text(encoding="utf-8")
    items = _ddl_items(text)
    assert len(items) == 11, items
    assert items.count("idx_project_custom_fields_project") == 1, items
    assert items.count("idx_project_task_field_values_field") == 1, items
    assert "UPDATE _schema_version SET version = 20;" in text


def test_migration_020_has_no_default_column_on_custom_fields():
    """S-9: a ``default`` column is explicitly out of the frozen DDL."""
    text = (_migrations_dir() / SQLITE_FILE).read_text(encoding="utf-8")
    block = text.split("CREATE TABLE IF NOT EXISTS project_custom_fields", 1)[1].split(");", 1)[0]
    # ``NOT NULL DEFAULT 0`` on required/options/sort_order is fine — what S-9
    # forbids is a *column named* ``default``.
    assert re.search(r"^\s*default\s", block, re.M) is None, block


def test_migration_020_pg_twin_matches_the_sqlite_ddl():
    sqlite_text = (_migrations_dir() / SQLITE_FILE).read_text(encoding="utf-8")
    pg_text = (_migrations_dir() / PG_FILE).read_text(encoding="utf-8")
    assert _ddl_items(pg_text) == _ddl_items(sqlite_text)
    assert "UPDATE _schema_version SET version = 20;" in pg_text
    assert "ADD COLUMN IF NOT EXISTS" in pg_text
