"""Project task CRUD, the task state machine, and timeline writes (T2.3).

``timeline_events`` is the M16 trace, so every task mutation is asserted to
leave exactly one well-formed row.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.project_tasks import (
    TIMELINE_TASK_ASSIGNED,
    TIMELINE_TASK_CREATED,
    TIMELINE_TASK_DELETED,
    TIMELINE_TASK_STATUS_CHANGED,
    TIMELINE_TASK_UPDATED,
    ProjectTaskRepo,
    TimelineRepo,
    actor_ref,
)
from octop.infra.db.repos.projects import MEMBER_SUBJECT_USER, ProjectMemberRepo, ProjectRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge import service as knowledge_service_module
from octop.infra.projects import service as project_service_module
from octop.infra.projects.service import PROJECT_READ, PROJECT_WRITE, ProjectService
from octop.infra.utils.paths import PathLayout


class Actor:
    def __init__(
        self, user_id: int, *, admin: bool = False, permissions: list[str] | None = None
    ) -> None:
        self.id = user_id
        self._admin = admin
        self.permissions = ["projects", "knowledge_bases"] if permissions is None else permissions

    @property
    def is_admin(self) -> bool:
        return self._admin


@pytest.fixture
def services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    monkeypatch.setattr(knowledge_service_module, "assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(
        project_service_module, "get_capability", lambda *_a, **_k: {"usable": True}
    )
    return SimpleNamespace(
        db=pool,
        project_repo=ProjectRepo(pool),
        project_member_repo=ProjectMemberRepo(pool),
        project_task_repo=ProjectTaskRepo(pool),
        timeline_repo=TimelineRepo(pool),
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
        agent_repo=AgentRepo(pool),
        thread_repo=ThreadRepo(pool),
        paths=PathLayout.from_env(),
    )


@pytest.fixture
def service(services: SimpleNamespace) -> ProjectService:
    return ProjectService(services)


@pytest.fixture
def owner(services: SimpleNamespace) -> Actor:
    return Actor(services.user_repo.create(username="owner", password_hash="h", role="user"))


@pytest.fixture
def project(service: ProjectService, owner: Actor) -> Any:
    return service.create_project(owner_user=owner, name="Alpha")


def actions(service: ProjectService, project_id: str, owner: Actor) -> list[str]:
    return [e.action for e in service.list_timeline(project_id, user=owner)]


# ── create ───────────────────────────────────────────────────────────────────


def test_create_task_starts_in_planning_and_records_timeline(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="Write the spec")

    assert task.status == "planning"
    assert task.project_id == project.id
    assert task.created_by == owner.id
    assert task.sort_order == 0

    events = service.list_timeline(project.id, user=owner)
    assert [e.action for e in events] == [TIMELINE_TASK_CREATED]
    assert events[0].task_id == task.id
    assert events[0].actor == actor_ref("user", owner.id)
    assert events[0].payload == {"title": "Write the spec"}


def test_create_task_rejects_a_blank_title(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    with pytest.raises(ValueError, match="task title is required"):
        service.create_task(project.id, user=owner, title="   ")


def test_create_task_rejects_a_status_outside_the_vocabulary(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    """Any of the seven states may be chosen up front (R2); anything else is 409."""
    for status in ("done", "review"):
        assert (
            service.create_task(project.id, user=owner, title="T", status=status).status == status
        )
    with pytest.raises(OctopError) as err:
        service.create_task(project.id, user=owner, title="T", status="exploded")
    assert err.value.code is ErrorCode.PROJECT_TASK_STATUS_INVALID
    assert err.value.status == 409


def test_create_task_accepts_explicit_todo(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T", status="todo")
    assert task.status == "todo"


def test_create_task_carries_optional_fields(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(
        project.id,
        user=owner,
        title="T",
        description="d",
        priority=3,
        deps=["x"],
        due_at=1234,
    )
    assert (task.description, task.priority, task.deps, task.due_at) == ("d", 3, ("x",), 1234)


def test_task_sort_order_is_per_project(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    a = service.create_task(project.id, user=owner, title="1")
    b = service.create_task(project.id, user=owner, title="2")
    assert (a.sort_order, b.sort_order) == (0, 1)


def test_create_task_requires_write(
    service: ProjectService, services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    viewer = Actor(services.user_repo.create(username="viewer", password_hash="h", role="user"))
    service.add_member(
        project.id,
        user=owner,
        subject_type=MEMBER_SUBJECT_USER,
        subject_id=str(viewer.id),
        role="viewer",
        subject_user_id=viewer.id,
    )
    with pytest.raises(OctopError) as err:
        service.create_task(project.id, user=viewer, title="T")
    assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN


# ── soft foreign keys ────────────────────────────────────────────────────────


def test_parent_task_must_exist(service: ProjectService, project: Any, owner: Actor) -> None:
    with pytest.raises(OctopError) as err:
        service.create_task(project.id, user=owner, title="child", parent_id="nope")
    assert err.value.code is ErrorCode.PROJECT_TASK_NOT_FOUND
    assert err.value.status == 404
    assert err.value.status != 500


def test_parent_task_must_belong_to_the_same_project(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    other = service.create_project(owner_user=owner, name="Beta")
    foreign_parent = service.create_task(other.id, user=owner, title="elsewhere")

    with pytest.raises(OctopError) as err:
        service.create_task(project.id, user=owner, title="child", parent_id=foreign_parent.id)
    assert err.value.code is ErrorCode.PROJECT_TASK_NOT_FOUND
    assert err.value.status == 404
    assert err.value.status != 500


def test_task_can_nest_in_its_own_project(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    parent = service.create_task(project.id, user=owner, title="parent")
    child = service.create_task(project.id, user=owner, title="child", parent_id=parent.id)
    assert child.parent_id == parent.id


def test_task_cannot_be_its_own_parent(service: ProjectService, project: Any, owner: Actor) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    with pytest.raises(OctopError) as err:
        service.update_task(project.id, task.id, user=owner, parent_id=task.id)
    assert err.value.code is ErrorCode.PROJECT_TASK_NOT_FOUND
    assert err.value.status != 500


def test_unknown_thread_is_rejected(service: ProjectService, project: Any, owner: Actor) -> None:
    with pytest.raises(OctopError) as err:
        service.create_task(project.id, user=owner, title="T", thread_id="th_missing")
    assert err.value.code is ErrorCode.PROJECT_TASK_THREAD_NOT_FOUND
    assert err.value.status == 404
    assert err.value.status != 500


def test_unknown_thread_is_rejected_on_the_update_path_too(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    """``update`` takes the same soft-FK check, so it must answer the same code."""
    task = service.create_task(project.id, user=owner, title="T")

    with pytest.raises(OctopError) as err:
        service.update_task(project.id, task.id, user=owner, thread_id="th_missing")

    assert err.value.code is ErrorCode.PROJECT_TASK_THREAD_NOT_FOUND
    assert err.value.status == 404
    assert err.value.status != 500
    assert service.get_task(project.id, task.id, user=owner).thread_id is None


def _insert_thread(services: SimpleNamespace, thread_id: str, user_id: int) -> None:
    """A dashboard thread for ``user_id``; threads.agent_id is a hard FK."""
    services.agent_repo.create(agent_id=f"ag-{thread_id}", user_id=user_id, name="Agent")
    services.thread_repo.insert(
        thread_id=thread_id,
        agent_id=f"ag-{thread_id}",
        user_id=user_id,
        channel_type="dashboard",
        session_key=f"sk-{thread_id}",
    )


def test_known_thread_is_accepted(
    service: ProjectService, services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    _insert_thread(services, "th1", owner.id)
    task = service.create_task(project.id, user=owner, title="T", thread_id="th1")
    assert task.thread_id == "th1"
    assert [t.id for t in services.project_task_repo.list_by_thread("th1")] == [task.id]


# ── state machine ────────────────────────────────────────────────────────────


def test_happy_path_todo_doing_review_done(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T", status="todo")
    for target in ("doing", "review", "done"):
        assert (
            service.transition_task(project.id, task.id, user=owner, target=target).status == target
        )

    assert actions(service, project.id, owner) == [
        TIMELINE_TASK_CREATED,
        TIMELINE_TASK_STATUS_CHANGED,
        TIMELINE_TASK_STATUS_CHANGED,
        TIMELINE_TASK_STATUS_CHANGED,
    ]
    events = service.list_timeline(project.id, user=owner)
    assert [e.payload for e in events[1:]] == [
        {"from": "todo", "to": "doing"},
        {"from": "doing", "to": "review"},
        {"from": "review", "to": "done"},
    ]


def test_todo_cannot_jump_to_done(service: ProjectService, project: Any, owner: Actor) -> None:
    task = service.create_task(project.id, user=owner, title="T", status="todo")
    with pytest.raises(OctopError) as err:
        service.transition_task(project.id, task.id, user=owner, target="done")
    assert err.value.code is ErrorCode.PROJECT_TASK_STATUS_INVALID
    assert service.get_task(project.id, task.id, user=owner).status == "todo"


def test_blocked_is_reachable_and_recoverable(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T", status="todo")
    assert (
        service.transition_task(project.id, task.id, user=owner, target="blocked").status
        == "blocked"
    )
    assert (
        service.transition_task(project.id, task.id, user=owner, target="doing").status == "doing"
    )
    assert (
        service.transition_task(project.id, task.id, user=owner, target="blocked").status
        == "blocked"
    )
    assert service.transition_task(project.id, task.id, user=owner, target="todo").status == "todo"


def test_done_can_only_be_reopened_to_doing(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T", status="todo")
    service.transition_task(project.id, task.id, user=owner, target="doing")
    service.transition_task(project.id, task.id, user=owner, target="done")

    for target in ("todo", "review", "blocked"):
        with pytest.raises(OctopError) as err:
            service.transition_task(project.id, task.id, user=owner, target=target)
        assert err.value.code is ErrorCode.PROJECT_TASK_STATUS_INVALID

    assert (
        service.transition_task(project.id, task.id, user=owner, target="doing").status == "doing"
    )


def test_cancelled_is_terminal(service: ProjectService, project: Any, owner: Actor) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    service.transition_task(project.id, task.id, user=owner, target="cancelled")
    for target in ("todo", "doing", "review", "done", "blocked", "cancelled"):
        with pytest.raises(OctopError) as err:
            service.transition_task(project.id, task.id, user=owner, target=target)
        assert err.value.code is ErrorCode.PROJECT_TASK_STATUS_INVALID


def test_unknown_task_status_is_rejected_with_its_code(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    with pytest.raises(OctopError) as err:
        service.transition_task(project.id, task.id, user=owner, target="exploded")
    assert err.value.code is ErrorCode.PROJECT_TASK_STATUS_INVALID
    assert err.value.status == 409, "an unknown enum value is a 4xx, never a 500"


def test_no_timeline_row_when_the_transition_is_rejected(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    with pytest.raises(OctopError):
        service.transition_task(project.id, task.id, user=owner, target="done")
    assert actions(service, project.id, owner) == [TIMELINE_TASK_CREATED]


def test_task_status_is_not_patchable_through_update_task(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    with pytest.raises(OctopError) as err:
        service.update_task(project.id, task.id, user=owner, status="done")
    assert err.value.code is ErrorCode.PROJECT_TASK_STATUS_INVALID
    assert err.value.status == 409, "status changes route through the state machine"


# ── update / delete ──────────────────────────────────────────────────────────


def test_update_task_patches_and_records(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    updated = service.update_task(project.id, task.id, user=owner, title="Renamed", priority=5)

    assert (updated.title, updated.priority) == ("Renamed", 5)
    events = service.list_timeline(project.id, user=owner)
    assert [e.action for e in events] == [TIMELINE_TASK_CREATED, TIMELINE_TASK_UPDATED]
    assert events[1].payload == {"fields": ["priority", "title"]}


def test_update_task_with_no_fields_is_a_noop(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    assert service.update_task(project.id, task.id, user=owner) == task
    assert actions(service, project.id, owner) == [TIMELINE_TASK_CREATED]


def test_assignment_records_its_own_event(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    service.update_task(
        project.id, task.id, user=owner, assignee_type="agent", assignee_id="agent-1"
    )

    events = service.list_timeline(project.id, user=owner)
    assert [e.action for e in events] == [
        TIMELINE_TASK_CREATED,
        TIMELINE_TASK_UPDATED,
        TIMELINE_TASK_ASSIGNED,
    ]
    assert events[-1].payload == {"assignee_type": "agent", "assignee_id": "agent-1"}


def test_delete_task_records_but_keeps_the_history(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    assert service.delete_task(project.id, task.id, user=owner) is True

    with pytest.raises(OctopError) as err:
        service.get_task(project.id, task.id, user=owner)
    assert err.value.code is ErrorCode.PROJECT_TASK_NOT_FOUND

    events = service.list_timeline(project.id, user=owner)
    assert [e.action for e in events] == [TIMELINE_TASK_CREATED, TIMELINE_TASK_DELETED]
    assert events[-1].task_id == task.id, "the deleted task id must survive in history"


def test_delete_unknown_task_is_not_found(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    with pytest.raises(OctopError) as err:
        service.delete_task(project.id, "nope", user=owner)
    assert err.value.code is ErrorCode.PROJECT_TASK_NOT_FOUND


# ── listing / permissions ────────────────────────────────────────────────────


def test_list_tasks_filters_by_status(service: ProjectService, project: Any, owner: Actor) -> None:
    first = service.create_task(project.id, user=owner, title="1", status="todo")
    service.create_task(project.id, user=owner, title="2", status="todo")
    service.transition_task(project.id, first.id, user=owner, target="doing")

    assert [t.title for t in service.list_tasks(project.id, user=owner)] == ["1", "2"]
    assert [t.title for t in service.list_tasks(project.id, user=owner, status="todo")] == ["2"]
    assert [t.title for t in service.list_tasks(project.id, user=owner, status="doing")] == ["1"]


def test_viewer_can_read_tasks_but_not_change_them(
    service: ProjectService, services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    viewer = Actor(services.user_repo.create(username="viewer", password_hash="h", role="user"))
    service.add_member(
        project.id,
        user=owner,
        subject_type=MEMBER_SUBJECT_USER,
        subject_id=str(viewer.id),
        role="viewer",
        subject_user_id=viewer.id,
    )

    assert [t.id for t in service.list_tasks(project.id, user=viewer)] == [task.id]
    assert service.get_task(project.id, task.id, user=viewer).id == task.id
    assert [e.action for e in service.list_timeline(project.id, user=viewer)] == [
        TIMELINE_TASK_CREATED
    ]

    for call in (
        lambda: service.transition_task(project.id, task.id, user=viewer, target="doing"),
        lambda: service.update_task(project.id, task.id, user=viewer, title="X"),
        lambda: service.delete_task(project.id, task.id, user=viewer),
    ):
        with pytest.raises(OctopError) as err:
            call()
        assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN
    assert service.assert_project_role(project.id, user=viewer, required=PROJECT_READ) == "viewer"
    with pytest.raises(OctopError):
        service.assert_project_role(project.id, user=viewer, required=PROJECT_WRITE)


def test_non_member_cannot_reach_a_task(
    service: ProjectService, services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    outsider = Actor(services.user_repo.create(username="out", password_hash="h", role="user"))

    with pytest.raises(OctopError) as err:
        service.get_task(project.id, task.id, user=outsider)
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN


def test_archived_project_makes_tasks_read_only(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    service.transition_project(project.id, user=owner, target="active")
    service.transition_project(project.id, user=owner, target="archived")

    assert service.get_task(project.id, task.id, user=owner).id == task.id
    with pytest.raises(OctopError) as err:
        service.transition_task(project.id, task.id, user=owner, target="doing")
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN


def test_timeline_limit(service: ProjectService, project: Any, owner: Actor) -> None:
    for i in range(3):
        service.create_task(project.id, user=owner, title=f"T{i}")
    assert len(service.list_timeline(project.id, user=owner, limit=2)) == 2


def test_timeline_is_ordered_oldest_first(
    service: ProjectService, services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    first = service.create_task(project.id, user=owner, title="1", status="todo")
    second = service.create_task(project.id, user=owner, title="2")
    service.transition_task(project.id, first.id, user=owner, target="doing")

    events = service.list_timeline(project.id, user=owner)
    assert [e.task_id for e in events] == [first.id, second.id, first.id]
    assert [e.pk for e in events] == sorted(e.pk for e in events)
