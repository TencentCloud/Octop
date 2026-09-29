"""Migration 025: expert-team runs, task findings, and task/artifact columns.

``team_runs`` is the 1:1 extension row of the project a team run owns -- it is not a
second project entity, so ``project_id`` is ``NOT NULL UNIQUE ... ON DELETE CASCADE``
(1:1 and same-lifetime, matching ``project_tasks.project_id``). Added are four tables
(``team_runs`` / ``team_run_phases`` / ``team_run_members`` / ``project_task_findings``),
thirteen ``project_tasks`` columns, two ``project_artifacts`` columns and one ``threads``
column. All additive -- no table rebuild, no ``migrate.py`` helper.

The "at most one lead per run" rule is a PARTIAL UNIQUE INDEX; a partial predicate is
not expressible as an inline table constraint in either dialect, so it is emitted as a
separate ``CREATE UNIQUE INDEX ... WHERE is_lead = 1``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool

NEW_TABLES = ("team_runs", "team_run_phases", "team_run_members", "project_task_findings")

TASK_COLUMNS = (
    "kind",
    "acceptance",
    "in_scope",
    "verify",
    "changed_paths",
    "round",
    "verdict",
    "attempt",
    "attempt_id",
    "claimed_by",
    "claimed_at",
    "started_at",
    "phase",
)


def _version(pool: SqlitePool) -> int:
    with pool.connect() as conn:
        return int(conn.execute("SELECT version FROM _schema_version").fetchone()["version"])


def _columns(pool: SqlitePool, table: str) -> set[str]:
    with pool.connect() as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _object_sql(pool: SqlitePool, name: str) -> str:
    with pool.connect() as conn:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (name,)).fetchone()
    assert row is not None, f"{name} is missing from sqlite_master"
    return str(row["sql"])


def test_head_is_25(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    assert _version(pool) == 25


def test_the_four_new_tables_exist(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    with pool.connect() as conn:
        names = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert set(NEW_TABLES) <= names


def test_project_tasks_gains_the_thirteen_columns(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    cols = _columns(pool, "project_tasks")
    assert set(TASK_COLUMNS) <= cols
    # ``started_at`` (actual start) and the pre-existing ``start_at`` (planned start
    # day) are different facts and must coexist.
    assert "start_at" in cols
    assert len(TASK_COLUMNS) == 13


def test_project_artifacts_gains_owner_role_and_phase_but_not_artifact_name(
    tmp_path: Path,
) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    cols = _columns(pool, "project_artifacts")
    assert {"owner_role", "phase"} <= cols
    # The artifact name reuses the existing ``name`` column -- no second name column.
    assert "artifact_name" not in cols


def test_threads_gains_pending_decision(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    assert "pending_decision" in _columns(pool, "threads")


def test_team_runs_project_id_is_not_null_unique_cascade(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    table_sql = " ".join(_object_sql(pool, "team_runs").split())
    assert "project_id TEXT NOT NULL UNIQUE REFERENCES projects(project_id) ON DELETE CASCADE" in (
        table_sql
    ), table_sql


def test_at_most_one_lead_per_run(tmp_path: Path) -> None:
    db = tmp_path / "octop.db"
    pool = SqlitePool(db)
    run_migrations(pool)
    pool.close()

    # A raw connection lets us relax FK enforcement without building project/user
    # fixtures; the partial unique index is independent of FK enforcement.
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "INSERT INTO team_run_members (run_id, role, agent_id, is_lead, joined_at)"
            " VALUES ('r1', 'lead', 'a1', 1, 0)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO team_run_members (run_id, role, agent_id, is_lead, joined_at)"
                " VALUES ('r1', 'lead2', 'a2', 1, 0)"
            )
        # Any number of non-lead members stay allowed.
        for role, agent in (("dev", "a3"), ("qa", "a4")):
            conn.execute(
                "INSERT INTO team_run_members (run_id, role, agent_id, is_lead, joined_at)"
                " VALUES ('r1', ?, ?, 0, 0)",
                (role, agent),
            )
        conn.commit()
    finally:
        conn.close()


def test_rerunning_migrations_is_idempotent(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    before = _columns(pool, "project_tasks")
    run_migrations(pool)
    assert _version(pool) == 25
    assert _columns(pool, "project_tasks") == before


def test_the_pair_is_self_contained_on_both_dialects() -> None:
    sqlite_sql = Path("src/octop/infra/db/migrations/025_team_runs.sql").read_text(encoding="utf-8")
    pg_sql = Path("src/octop/infra/db/migrations/025_team_runs.pg.sql").read_text(encoding="utf-8")
    for text in (sqlite_sql, pg_sql):
        assert "CREATE TABLE IF NOT EXISTS team_runs" in text
        assert "CREATE TABLE IF NOT EXISTS team_run_members" in text
        assert "CREATE TABLE IF NOT EXISTS project_task_findings" in text
        assert (
            "ADD COLUMN started_at INTEGER" in text or "ADD COLUMN IF NOT EXISTS started_at" in text
        )
        assert "WHERE is_lead = 1" in text, "the lead rule must be a partial unique index"
        assert "UPDATE _schema_version SET version = 25;" in text
    assert "ALTER TABLE project_tasks ADD COLUMN kind TEXT NOT NULL DEFAULT 'work';" in sqlite_sql
    assert (
        "ALTER TABLE project_tasks ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'work';"
        in pg_sql
    ), "the PG twin must guard the column"
    for statement in pg_sql.split(";\n"):
        body = "\n".join(
            line for line in statement.splitlines() if not line.strip().startswith("--")
        ).strip()
        if body:
            assert body.upper().startswith(
                ("CREATE TABLE", "CREATE INDEX", "CREATE UNIQUE INDEX", "ALTER TABLE", "UPDATE")
            ), body


def test_no_migrate_helper_was_added() -> None:
    migrate = Path("src/octop/infra/db/migrate.py").read_text(encoding="utf-8")
    for token in ("team_runs", "team_run_members", "pending_decision", "project_task_findings"):
        assert token not in migrate, f"025 must slot into the generic SQL path (saw {token})"
