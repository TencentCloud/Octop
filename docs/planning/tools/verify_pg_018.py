# -*- coding: utf-8 -*-
"""Verify migration 018 against a real PostgreSQL database.

The SQLite path is covered by tests/unit/db/test_migration_018.py; PostgreSQL
executes 018_projects.pg.sql instead, so exercise that file directly:

  1. run_migrations on an empty database  -> 10 project tables + version 18
  2. run_migrations again                 -> idempotent
  3. drop the tables, run again           -> repair path recreates them
  4. confirm ``threads`` was not altered
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

from octop.infra.db.migrate import run_migrations  # noqa: E402
from octop.infra.db.pool import PostgresPool  # noqa: E402

DSN = "postgresql://octop:octop_dev_pw@127.0.0.1:5432/octop_v18_probe"

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


def tables(pool: PostgresPool) -> set[str]:
    with pool.connect() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema()"
        ).fetchall()
    return {str(r["table_name"]) for r in rows}


def version(pool: PostgresPool) -> int:
    with pool.connect() as conn:
        row = conn.execute("SELECT version FROM _schema_version").fetchone()
    return int(row["version"])


def report(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}{(' -- ' + detail) if detail else ''}")


def main() -> int:
    pool = PostgresPool(DSN)
    failures = 0
    try:
        print("1) fresh database -> run_migrations")
        run_migrations(pool)
        names = tables(pool)
        missing = sorted(set(PROJECT_TABLES) - names)
        ok = not missing and version(pool) == 18
        report("version == 18", version(pool) == 18, f"got {version(pool)}")
        report("10 project tables exist", not missing, f"missing={missing}" if missing else "")
        failures += 0 if ok else 1

        print("2) re-run -> idempotent")
        try:
            run_migrations(pool)
            report("second run raises nothing", True)
        except Exception as exc:  # noqa: BLE001
            report("second run raises nothing", False, repr(exc))
            failures += 1

        print("3) drop tables -> repair path recreates them")
        with pool.connect() as conn:
            for t in PROJECT_TABLES:
                conn.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        gone = not (set(PROJECT_TABLES) & tables(pool))
        report("tables dropped", gone)
        run_migrations(pool)
        back = not (set(PROJECT_TABLES) - tables(pool))
        report("repair recreated all tables", back)
        failures += 0 if back else 1

        print("4) threads not altered")
        with pool.connect() as conn:
            rows = conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'threads'"
            ).fetchall()
        cols = {str(r["column_name"]) for r in rows}
        has_project = "project_id" in cols
        has_v17 = {"conversation_mode", "pending_plan_path", "hitl_policy"} <= cols
        report("threads has no project_id", not has_project)
        report("threads keeps v17 columns", has_v17)
        failures += 0 if (not has_project and has_v17) else 1

        print("5) foreign keys resolve (insert + cascade)")
        with pool.connect() as conn:
            uid = conn.execute(
                "INSERT INTO users(username, password_hash, role, created_at) "
                "VALUES ('v18probe', 'h', 'user', 0) RETURNING id"
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO projects (project_id, name, owner_user_id, memory_namespace,"
                " created_at, updated_at) VALUES ('prj_probe', 'P', %s, 'project_prj_probe', 1, 1)",
                (uid,),
            )
            conn.execute(
                "INSERT INTO project_tasks (task_id, project_id, title, created_by,"
                " created_at, updated_at) VALUES ('task_probe', 'prj_probe', 'T', %s, 1, 1)",
                (uid,),
            )
            conn.execute("DELETE FROM projects WHERE project_id = 'prj_probe'")
            left = conn.execute(
                "SELECT COUNT(*) AS n FROM project_tasks WHERE project_id = 'prj_probe'"
            ).fetchone()["n"]
            conn.execute("DELETE FROM users WHERE username = 'v18probe'")
        report("ON DELETE CASCADE works", int(left) == 0, f"rows left={left}")
        failures += 0 if int(left) == 0 else 1

    finally:
        pool.close()

    print(f"\n{'ALL PASSED' if failures == 0 else f'{failures} CHECK(S) FAILED'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
