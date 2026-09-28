# -*- coding: utf-8 -*-
"""Exercise TimelineRepo and the task soft-FK checks against PostgreSQL.

The unit suite runs on SQLite only. The PostgreSQL-specific risks here are:

  * ``insert_returning_id`` -- TimelineRepo.append relies on
    ``INSERT ... RETURNING id`` because the pg proxy has no ``cursor.lastrowid``
  * the existence SELECTs used for the soft foreign keys
  * JSON payload round-trip through the ``payload`` column
"""
from __future__ import annotations

import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

from octop.infra.db.migrate import run_migrations  # noqa: E402
from octop.infra.db.pool import PostgresPool  # noqa: E402
from octop.infra.db.repos.project_tasks import (  # noqa: E402
    TIMELINE_TASK_CREATED,
    TIMELINE_TASK_STATUS_CHANGED,
    ProjectTaskRepo,
    TimelineRepo,
    actor_ref,
)
from octop.infra.db.repos.projects import ProjectRepo  # noqa: E402
from octop.infra.db.repos.users import UserRepo  # noqa: E402

ADMIN_DSN = "postgresql://octop:octop_dev_pw@127.0.0.1:5432/octop"
PROBE_DB = "octop_timeline_probe"
PROBE_DSN = f"postgresql://octop:octop_dev_pw@127.0.0.1:5432/{PROBE_DB}"

_failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _failures
    if not ok:
        _failures += 1
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}{(' -- ' + detail) if detail else ''}")


def psql(sql: str) -> None:
    subprocess.run(["psql", ADMIN_DSN, "-tAc", sql], capture_output=True, check=False)


def main() -> int:
    psql(f'DROP DATABASE IF EXISTS "{PROBE_DB}"')
    psql(f'CREATE DATABASE "{PROBE_DB}"')

    pool = PostgresPool(PROBE_DSN)
    try:
        run_migrations(pool)
        owner = UserRepo(pool).create(username="pgowner", password_hash="h", role="user")
        project = ProjectRepo(pool).create(owner_user_id=owner, name="Alpha")
        tasks = ProjectTaskRepo(pool)
        timeline = TimelineRepo(pool)

        print("1) TimelineRepo.append (INSERT ... RETURNING id)")
        first = timeline.append(
            project_id=project.id,
            actor=actor_ref("user", owner),
            action=TIMELINE_TASK_CREATED,
            payload={"title": "T", "non_ascii": "项目"},
        )
        check("row returned", first.pk > 0, f"pk={first.pk}")
        check("payload round-trips", first.payload == {"title": "T", "non_ascii": "项目"}, str(first.payload))
        second = timeline.append(
            project_id=project.id,
            actor=actor_ref("user", owner),
            action=TIMELINE_TASK_STATUS_CHANGED,
            payload={"from": "todo", "to": "doing"},
        )
        check("ids increase", second.pk > first.pk, f"{first.pk} -> {second.pk}")

        print("2) ordering and counting")
        events = timeline.list_by_project(project.id)
        check("chronological", [e.pk for e in events] == sorted(e.pk for e in events))
        check("limit applies", len(timeline.list_by_project(project.id, limit=1)) == 1)
        check("count matches", timeline.count_by_project(project.id) == 2)

        print("3) soft foreign keys")
        ok = False
        try:
            tasks.create(project_id=project.id, title="T", created_by=owner, thread_id="nope")
        except ValueError as exc:
            ok = "does not exist" in str(exc)
        check("unknown thread rejected", ok)

        other = ProjectRepo(pool).create(owner_user_id=owner, name="Beta")
        foreign = tasks.create(project_id=other.id, title="elsewhere", created_by=owner)
        ok = False
        try:
            tasks.create(
                project_id=project.id, title="child", created_by=owner, parent_id=foreign.id
            )
        except ValueError as exc:
            ok = "another project" in str(exc)
        check("cross-project parent rejected", ok)

        task = tasks.create(project_id=project.id, title="T", created_by=owner)
        check("own-project parent accepted", tasks.create(
            project_id=project.id, title="child", created_by=owner, parent_id=task.id
        ).parent_id == task.id)

        print("4) timeline survives task deletion")
        timeline.append(
            project_id=project.id,
            actor=actor_ref("user", owner),
            action="task.deleted",
            task_id=task.id,
        )
        check("task deleted", tasks.delete(task.id) is True)
        check("history kept", len(timeline.list_by_task(task.id)) == 1)
    finally:
        pool.close()
        psql(f'DROP DATABASE IF EXISTS "{PROBE_DB}"')

    print(f"\n{'ALL PASSED' if _failures == 0 else f'{_failures} CHECK(S) FAILED'}")
    return 0 if _failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
