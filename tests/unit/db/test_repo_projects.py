"""Project domain repos — projects, members, and their tasks.

Repo layer only: SQL shape, id allocation, patch semantics (``UNSET`` = leave
alone, explicit ``None`` = clear), and the resource-table convention
(integer ``pk`` + public string id).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.project_tasks import TASK_STATUSES, ProjectTaskRepo
from octop.infra.db.repos.projects import (
    MEMBER_SUBJECT_AGENT,
    MEMBER_SUBJECT_USER,
    PROJECT_ROLES,
    PROJECT_STATUSES,
    ProjectMemberRepo,
    ProjectRepo,
    project_memory_namespace,
)
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def owner(db: SqlitePool) -> int:
    return UserRepo(db).create(username="owner", password_hash="h", role="user")


@pytest.fixture
def other(db: SqlitePool) -> int:
    return UserRepo(db).create(username="other", password_hash="h", role="user")


# ── constants mirror the migration ───────────────────────────────────────────


def test_public_constants_match_the_ddl_comments():
    assert PROJECT_ROLES == ("owner", "admin", "member", "viewer")
    assert PROJECT_STATUSES == ("draft", "active", "paused", "archived")
    assert TASK_STATUSES == ("todo", "doing", "review", "done", "blocked", "cancelled")


def test_memory_namespace_is_derived_from_the_project_id():
    assert project_memory_namespace("AB12CD") == "project_AB12CD"


# ── ProjectRepo ──────────────────────────────────────────────────────────────


def test_create_derives_memory_namespace_and_defaults(db: SqlitePool, owner: int):
    row = ProjectRepo(db).create(owner_user_id=owner, name="Alpha")
    assert row.id
    assert row.pk > 0
    assert row.name == "Alpha"
    assert row.goal == ""
    assert row.status == "draft"
    assert row.kb_id is None
    assert row.inject_version == 0
    assert row.memory_namespace == f"project_{row.id}"
    assert row.created_at == row.updated_at


def test_create_allocates_distinct_ids(db: SqlitePool, owner: int):
    repo = ProjectRepo(db)
    ids = {repo.create(owner_user_id=owner, name=f"P{i}").id for i in range(20)}
    assert len(ids) == 20


def test_get_returns_none_for_unknown_id(db: SqlitePool):
    assert ProjectRepo(db).get("nope") is None


def test_list_by_owner_is_scoped(db: SqlitePool, owner: int, other: int):
    repo = ProjectRepo(db)
    mine = repo.create(owner_user_id=owner, name="Mine")
    repo.create(owner_user_id=other, name="Theirs")
    listed = repo.list_by_owner(owner)
    assert [p.id for p in listed] == [mine.id]


def test_list_for_user_includes_owned_and_member_projects(db: SqlitePool, owner: int, other: int):
    projects = ProjectRepo(db)
    members = ProjectMemberRepo(db)
    owned = projects.create(owner_user_id=owner, name="Owned")
    invited = projects.create(owner_user_id=other, name="Invited")
    hidden = projects.create(owner_user_id=other, name="Hidden")
    members.add(
        project_id=invited.id,
        subject_type=MEMBER_SUBJECT_USER,
        subject_id=str(owner),
        role="member",
    )
    ids = {p.id for p in projects.list_for_user(owner)}
    assert ids == {owned.id, invited.id}
    assert hidden.id not in ids


def test_update_patches_only_named_fields(db: SqlitePool, owner: int):
    repo = ProjectRepo(db)
    row = repo.create(owner_user_id=owner, name="Alpha", goal="g")
    patched = repo.update(row.id, name="Beta")
    assert patched is not None
    assert patched.name == "Beta"
    assert patched.goal == "g"  # untouched
    assert patched.status == "draft"


def test_update_distinguishes_omit_from_explicit_none(db: SqlitePool, owner: int):
    repo = ProjectRepo(db)
    row = repo.create(owner_user_id=owner, name="Alpha", due_at=1234)

    omitted = repo.update(row.id, name="Beta")
    assert omitted is not None and omitted.due_at == 1234  # omitted -> kept

    cleared = repo.update(row.id, due_at=None)
    assert cleared is not None and cleared.due_at is None  # explicit None -> cleared


def test_update_with_no_fields_is_a_read(db: SqlitePool, owner: int):
    repo = ProjectRepo(db)
    row = repo.create(owner_user_id=owner, name="Alpha")
    assert repo.update(row.id) == row


def test_set_kb_id_roundtrips(db: SqlitePool, owner: int):
    repo = ProjectRepo(db)
    row = repo.create(owner_user_id=owner, name="Alpha")
    repo.set_kb_id(row.id, "kb1")
    got = repo.get(row.id)
    assert got is not None and got.kb_id == "kb1"
    repo.set_kb_id(row.id, None)
    got = repo.get(row.id)
    assert got is not None and got.kb_id is None


def test_bump_inject_version_is_monotonic(db: SqlitePool, owner: int):
    repo = ProjectRepo(db)
    row = repo.create(owner_user_id=owner, name="Alpha")
    assert repo.bump_inject_version(row.id) == 1
    assert repo.bump_inject_version(row.id) == 2


def test_delete_cascades_to_children(db: SqlitePool, owner: int):
    projects = ProjectRepo(db)
    members = ProjectMemberRepo(db)
    tasks = ProjectTaskRepo(db)
    row = projects.create(owner_user_id=owner, name="Alpha")
    members.add(
        project_id=row.id,
        subject_type=MEMBER_SUBJECT_USER,
        subject_id=str(owner),
        role="owner",
    )
    tasks.create(project_id=row.id, title="T", created_by=owner)

    assert projects.delete(row.id) is True

    assert projects.get(row.id) is None
    assert members.list_by_project(row.id) == []
    assert tasks.list_by_project(row.id) == []


def test_delete_unknown_returns_false(db: SqlitePool):
    assert ProjectRepo(db).delete("nope") is False


# ── ProjectMemberRepo ────────────────────────────────────────────────────────


def test_add_user_member_fills_user_id_from_subject_id(db: SqlitePool, owner: int):
    projects = ProjectRepo(db)
    project = projects.create(owner_user_id=owner, name="Alpha")
    member = ProjectMemberRepo(db).add(
        project_id=project.id,
        subject_type=MEMBER_SUBJECT_USER,
        subject_id=str(owner),
    )
    assert member.role == "member"
    assert member.user_id == owner


def test_add_agent_member_has_no_user_id(db: SqlitePool, owner: int):
    project = ProjectRepo(db).create(owner_user_id=owner, name="Alpha")
    member = ProjectMemberRepo(db).add(
        project_id=project.id,
        subject_type=MEMBER_SUBJECT_AGENT,
        subject_id="agent-1",
        role="member",
    )
    assert member.user_id is None
    assert member.subject_type == "agent"


def test_add_is_upsert_so_reinviting_changes_the_role(db: SqlitePool, owner: int):
    project = ProjectRepo(db).create(owner_user_id=owner, name="Alpha")
    members = ProjectMemberRepo(db)
    members.add(project_id=project.id, subject_type=MEMBER_SUBJECT_USER, subject_id=str(owner))
    members.add(
        project_id=project.id,
        subject_type=MEMBER_SUBJECT_USER,
        subject_id=str(owner),
        role="admin",
    )
    assert members.role_of(project.id, MEMBER_SUBJECT_USER, str(owner)) == "admin"
    assert members.count(project.id) == 1


def test_same_subject_can_join_two_projects(db: SqlitePool, owner: int):
    projects = ProjectRepo(db)
    members = ProjectMemberRepo(db)
    a = projects.create(owner_user_id=owner, name="A")
    b = projects.create(owner_user_id=owner, name="B")
    for project in (a, b):
        members.add(
            project_id=project.id,
            subject_type=MEMBER_SUBJECT_USER,
            subject_id=str(owner),
        )
    assert set(members.list_project_ids_for_subject(MEMBER_SUBJECT_USER, str(owner))) == {
        a.id,
        b.id,
    }


def test_remove_member(db: SqlitePool, owner: int):
    project = ProjectRepo(db).create(owner_user_id=owner, name="Alpha")
    members = ProjectMemberRepo(db)
    members.add(project_id=project.id, subject_type=MEMBER_SUBJECT_USER, subject_id=str(owner))
    assert members.remove(project.id, MEMBER_SUBJECT_USER, str(owner)) is True
    assert members.remove(project.id, MEMBER_SUBJECT_USER, str(owner)) is False
    assert members.role_of(project.id, MEMBER_SUBJECT_USER, str(owner)) is None


def test_role_of_unknown_subject_is_none(db: SqlitePool, owner: int):
    project = ProjectRepo(db).create(owner_user_id=owner, name="Alpha")
    assert ProjectMemberRepo(db).role_of(project.id, MEMBER_SUBJECT_USER, "999") is None


# ── ProjectTaskRepo ──────────────────────────────────────────────────────────


def test_task_sort_order_auto_increments_per_project(db: SqlitePool, owner: int):
    projects = ProjectRepo(db)
    tasks = ProjectTaskRepo(db)
    a = projects.create(owner_user_id=owner, name="A")
    b = projects.create(owner_user_id=owner, name="B")

    first = tasks.create(project_id=a.id, title="1", created_by=owner)
    second = tasks.create(project_id=a.id, title="2", created_by=owner)
    other_first = tasks.create(project_id=b.id, title="1", created_by=owner)

    assert (first.sort_order, second.sort_order) == (0, 1)
    assert other_first.sort_order == 0  # numbering is per project


def test_task_list_by_project_orders_by_sort_order(db: SqlitePool, owner: int):
    project = ProjectRepo(db).create(owner_user_id=owner, name="A")
    tasks = ProjectTaskRepo(db)
    tasks.create(project_id=project.id, title="third", created_by=owner, sort_order=9)
    tasks.create(project_id=project.id, title="first", created_by=owner, sort_order=1)
    titles = [t.title for t in tasks.list_by_project(project.id)]
    assert titles == ["first", "third"]


def test_task_list_filters_by_status(db: SqlitePool, owner: int):
    project = ProjectRepo(db).create(owner_user_id=owner, name="A")
    tasks = ProjectTaskRepo(db)
    tasks.create(project_id=project.id, title="todo one", created_by=owner)
    done = tasks.create(project_id=project.id, title="done one", created_by=owner)
    tasks.update(done.id, status="done")

    assert [t.title for t in tasks.list_by_project(project.id)] == ["todo one", "done one"]
    assert [t.title for t in tasks.list_by_project(project.id, status="done")] == ["done one"]


def test_task_deps_round_trip_as_a_tuple(db: SqlitePool, owner: int):
    project = ProjectRepo(db).create(owner_user_id=owner, name="A")
    tasks = ProjectTaskRepo(db)
    task = tasks.create(
        project_id=project.id,
        title="T",
        created_by=owner,
        deps=["a", "b"],
    )
    assert task.deps == ("a", "b")

    updated = tasks.update(task.id, deps=["c"])
    assert updated is not None and updated.deps == ("c",)

    omitted = tasks.update(task.id, title="renamed")
    assert omitted is not None and omitted.deps == ("c",)


def test_task_update_distinguishes_omit_from_explicit_none(db: SqlitePool, owner: int):
    project = ProjectRepo(db).create(owner_user_id=owner, name="A")
    tasks = ProjectTaskRepo(db)
    task = tasks.create(
        project_id=project.id,
        title="T",
        created_by=owner,
        assignee_type="agent",
        assignee_id="agent-1",
    )

    kept = tasks.update(task.id, title="renamed")
    assert kept is not None and kept.assignee_id == "agent-1"

    cleared = tasks.update(task.id, assignee_id=None)
    assert cleared is not None and cleared.assignee_id is None


def test_task_list_by_thread(db: SqlitePool, owner: int):
    project = ProjectRepo(db).create(owner_user_id=owner, name="A")
    tasks = ProjectTaskRepo(db)
    # thread_id is a soft foreign key, so the thread has to exist first —
    # and threads.agent_id is a hard FK, hence the agent row.
    AgentRepo(db).create(agent_id="a1", user_id=owner, name="Agent 1")
    ThreadRepo(db).insert(
        thread_id="th1",
        agent_id="a1",
        user_id=owner,
        channel_type="dashboard",
        session_key="sk-th1",
    )
    linked = tasks.create(project_id=project.id, title="linked", created_by=owner, thread_id="th1")
    tasks.create(project_id=project.id, title="loose", created_by=owner)
    assert [t.id for t in tasks.list_by_thread("th1")] == [linked.id]


def test_task_thread_must_exist(db: SqlitePool, owner: int):
    """Soft foreign key: a bogus thread_id is rejected, not silently stored."""
    project = ProjectRepo(db).create(owner_user_id=owner, name="A")
    with pytest.raises(ValueError, match="does not exist"):
        ProjectTaskRepo(db).create(
            project_id=project.id, title="T", created_by=owner, thread_id="nope"
        )


def test_task_parent_must_be_in_the_same_project(db: SqlitePool, owner: int):
    projects = ProjectRepo(db)
    tasks = ProjectTaskRepo(db)
    a = projects.create(owner_user_id=owner, name="A")
    b = projects.create(owner_user_id=owner, name="B")
    foreign = tasks.create(project_id=b.id, title="elsewhere", created_by=owner)

    with pytest.raises(ValueError, match="belongs to another project"):
        tasks.create(project_id=a.id, title="child", created_by=owner, parent_id=foreign.id)


def test_task_delete(db: SqlitePool, owner: int):
    project = ProjectRepo(db).create(owner_user_id=owner, name="A")
    tasks = ProjectTaskRepo(db)
    task = tasks.create(project_id=project.id, title="T", created_by=owner)
    assert tasks.delete(task.id) is True
    assert tasks.delete(task.id) is False
    assert tasks.get(task.id) is None
