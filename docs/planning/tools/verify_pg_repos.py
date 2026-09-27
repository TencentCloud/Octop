# -*- coding: utf-8 -*-
"""Exercise the project repos against PostgreSQL.

The unit suite runs on SQLite only. Three things behave differently on PG and
are worth proving on a real server:

  * ``?`` -> ``%s`` placeholder rewriting in ``_PgConnectionProxy``
  * ``ON CONFLICT(...) DO UPDATE`` upsert in ProjectMemberRepo.add
  * ``cursor.rowcount`` as seen through the proxy (delete/remove return values)
  * JSON ``deps`` round-trip and the ``NULL``-vs-omitted patch semantics
"""
from __future__ import annotations

import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

from octop.infra.db.migrate import run_migrations  # noqa: E402
from octop.infra.db.pool import PostgresPool  # noqa: E402
from octop.infra.db.repos.project_tasks import ProjectTaskRepo  # noqa: E402
from octop.infra.db.repos.projects import (  # noqa: E402
    MEMBER_SUBJECT_USER,
    ProjectMemberRepo,
    ProjectRepo,
)
from octop.infra.db.repos.users import UserRepo  # noqa: E402

ADMIN_DSN = "postgresql://octop:octop_dev_pw@127.0.0.1:5432/octop"
PROBE_DB = "octop_repo_probe"
PROBE_DSN = f"postgresql://octop:octop_dev_pw@127.0.0.1:5432/{PROBE_DB}"

_failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _failures
    if not ok:
        _failures += 1
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}{(' -- ' + detail) if detail else ''}")


def psql(sql: str, dsn: str = ADMIN_DSN) -> None:
    subprocess.run(["psql", dsn, "-tAc", sql], capture_output=True, check=False)


def main() -> int:
    psql(f'DROP DATABASE IF EXISTS "{PROBE_DB}"')
    psql(f'CREATE DATABASE "{PROBE_DB}"')

    pool = PostgresPool(PROBE_DSN)
    try:
        run_migrations(pool)
        users = UserRepo(pool)
        owner = users.create(username="pgowner", password_hash="h", role="user")
        other = users.create(username="pgother", password_hash="h", role="user")

        projects = ProjectRepo(pool)
        members = ProjectMemberRepo(pool)
        tasks = ProjectTaskRepo(pool)

        print("1) ProjectRepo.create / get")
        row = projects.create(owner_user_id=owner, name="Alpha", goal="g", due_at=99)
        check("id allocated", bool(row.id))
        check("memory_namespace derived", row.memory_namespace == f"project_{row.id}")
        check("get round-trips", projects.get(row.id) == row)

        print("2) patch semantics (omit vs explicit NULL)")
        kept = projects.update(row.id, name="Beta")
        check("omitted due_at kept", kept is not None and kept.due_at == 99)
        cleared = projects.update(row.id, due_at=None)
        check("explicit None clears", cleared is not None and cleared.due_at is None)

        print("3) ProjectMemberRepo upsert (ON CONFLICT DO UPDATE)")
        members.add(
            project_id=row.id,
            subject_type=MEMBER_SUBJECT_USER,
            subject_id=str(owner),
            role="member",
        )
        members.add(
            project_id=row.id,
            subject_type=MEMBER_SUBJECT_USER,
            subject_id=str(owner),
            role="admin",
        )
        check("role upserted", members.role_of(row.id, MEMBER_SUBJECT_USER, str(owner)) == "admin")
        check("no duplicate row", members.count(row.id) == 1)
        check("user_id inferred", members.get(row.id, MEMBER_SUBJECT_USER, str(owner)).user_id == owner)  # type: ignore[union-attr]

        print("4) list_for_user join")
        invited = projects.create(owner_user_id=other, name="Invited")
        members.add(
            project_id=invited.id,
            subject_type=MEMBER_SUBJECT_USER,
            subject_id=str(owner),
        )
        ids = {p.id for p in projects.list_for_user(owner)}
        check("owned + member visible", ids == {row.id, invited.id}, f"got {ids}")

        print("5) tasks: JSON deps, per-project sort_order, status filter")
        first = tasks.create(project_id=row.id, title="T1", created_by=owner, deps=["a", "b"])
        second = tasks.create(project_id=row.id, title="T2", created_by=owner)
        check("deps round-trip", first.deps == ("a", "b"), f"got {first.deps}")
        check("sort_order increments", (first.sort_order, second.sort_order) == (0, 1))
        tasks.update(second.id, status="done")
        check(
            "status filter",
            [t.title for t in tasks.list_by_project(row.id, status="done")] == ["T2"],
        )
        patched = tasks.update(first.id, deps=[])
        check("deps patch", patched is not None and patched.deps == ())

        print("6) rowcount through the proxy")
        check("task delete returns True", tasks.delete(first.id) is True)
        check("task delete again returns False", tasks.delete(first.id) is False)
        check("member remove returns True", members.remove(row.id, MEMBER_SUBJECT_USER, str(owner)) is True)
        check("project delete returns True", projects.delete(invited.id) is True)
        check("project delete again returns False", projects.delete(invited.id) is False)

        print("7) cascade on PG")
        # ``row`` still owns the second task and an invited member; deleting it
        # must take both with it via the ON DELETE CASCADE foreign keys.
        members.add(
            project_id=row.id,
            subject_type=MEMBER_SUBJECT_USER,
            subject_id=str(other),
            role="member",
        )
        check("precondition: row has a task", len(tasks.list_by_project(row.id)) == 1)
        check("precondition: row has a member", len(members.list_by_project(row.id)) == 1)
        check("delete row", projects.delete(row.id) is True)
        check("tasks cascaded", tasks.list_by_project(row.id) == [])
        check("members cascaded", members.list_by_project(row.id) == [])

    finally:
        pool.close()
        psql(f'DROP DATABASE IF EXISTS "{PROBE_DB}"')

    print(f"\n{'ALL PASSED' if _failures == 0 else f'{_failures} CHECK(S) FAILED'}")
    return 0 if _failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
