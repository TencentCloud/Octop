"""State machine v2 guards — seven task states, six project states (PLAN.md §1/§3).

The graph itself is the contract, so these tests assert the *shape* (keys, edges,
terminal sets, in-edges) as well as the observable behaviour over the service:
illegal moves are 409, never a 500.

Fixtures mirror ``test_project_tasks.py``: a real migrated SQLite pool with the
knowledge feature stubbed on.
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
from octop.infra.db.repos.project_tasks import TASK_STATUSES, ProjectTaskRepo, TimelineRepo
from octop.infra.db.repos.projects import PROJECT_STATUSES, ProjectMemberRepo, ProjectRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge import service as knowledge_service_module
from octop.infra.projects import service as project_service_module
from octop.infra.projects.service import (
    _TASK_TRANSITIONS,
    _TRANSITIONS,
    PROJECT_WRITE,
    ProjectService,
)
from octop.infra.utils.paths import PathLayout

TASK_VOCABULARY = ("planning", "todo", "doing", "review", "done", "blocked", "cancelled")
PROJECT_VOCABULARY = ("draft", "active", "paused", "completed", "cancelled", "archived")


class Actor:
    def __init__(self, user_id: int, *, permissions: list[str] | None = None) -> None:
        self.id = user_id
        self._admin = False
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


def _in_edges(graph: dict[str, frozenset[str]], target: str) -> set[str]:
    return {source for source, edges in graph.items() if target in edges}


# ── task vocabulary and graph shape (PLAN.md §1) ─────────────────────────────


def test_task_vocabulary_is_the_frozen_seven():
    assert TASK_STATUSES == TASK_VOCABULARY


def test_task_transition_keys_match_the_vocabulary():
    """A missing key would make that status unreachable *and* a dead end."""
    assert set(_TASK_TRANSITIONS) == set(TASK_STATUSES)


def test_task_transition_edges_stay_inside_the_vocabulary():
    for source, edges in _TASK_TRANSITIONS.items():
        assert edges <= set(TASK_STATUSES), source


def test_planning_in_edges_are_creation_and_todo_only():
    """``doing``/``review``/``done``/``blocked``/``cancelled`` must not reach it."""
    assert _in_edges(_TASK_TRANSITIONS, "planning") == {"todo"}
    assert _TASK_TRANSITIONS["planning"] == frozenset({"todo", "cancelled"})


def test_terminal_and_legacy_adjacency_is_preserved():
    assert _TASK_TRANSITIONS["cancelled"] == frozenset()
    assert _TASK_TRANSITIONS["done"] == frozenset({"doing"})
    assert _TASK_TRANSITIONS["doing"] == frozenset(
        {"todo", "review", "done", "blocked", "cancelled"}
    )


# ── creation semantics (PLAN.md §2.1) ────────────────────────────────────────


def test_create_defaults_to_planning(service: ProjectService, project: Any, owner: Actor) -> None:
    assert service.create_task(project.id, user=owner, title="T").status == "planning"


@pytest.mark.parametrize("target", TASK_VOCABULARY)
def test_every_column_can_be_created_directly(
    service: ProjectService, project: Any, owner: Actor, target: str
) -> None:
    task = service.create_task(project.id, user=owner, title="T", status=target)
    assert task.status == target


def test_unknown_initial_status_is_a_409_not_a_500(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    with pytest.raises(OctopError) as err:
        service.create_task(project.id, user=owner, title="T", status="exploded")
    assert err.value.code is ErrorCode.PROJECT_TASK_STATUS_INVALID
    assert err.value.status == 409
    assert err.value.status != 500


# ── transitions over the service ─────────────────────────────────────────────


def test_planning_can_be_scheduled_and_reopened(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    task = service.create_task(project.id, user=owner, title="T")

    assert service.transition_task(project.id, task.id, user=owner, target="todo").status == "todo"
    assert (
        service.transition_task(project.id, task.id, user=owner, target="planning").status
        == "planning"
    )


def test_planning_can_be_cancelled(service: ProjectService, project: Any, owner: Actor) -> None:
    task = service.create_task(project.id, user=owner, title="T")
    assert (
        service.transition_task(project.id, task.id, user=owner, target="cancelled").status
        == "cancelled"
    )


@pytest.mark.parametrize(
    ("initial", "target"),
    [
        ("planning", "done"),
        ("planning", "doing"),
        ("todo", "done"),
        ("cancelled", "todo"),
    ],
)
def test_illegal_transitions_are_409_not_500(
    service: ProjectService,
    project: Any,
    owner: Actor,
    initial: str,
    target: str,
) -> None:
    task = service.create_task(project.id, user=owner, title="T", status=initial)

    with pytest.raises(OctopError) as err:
        service.transition_task(project.id, task.id, user=owner, target=target)

    assert err.value.code is ErrorCode.PROJECT_TASK_STATUS_INVALID
    assert err.value.status == 409
    assert err.value.status != 500
    assert service.get_task(project.id, task.id, user=owner).status == initial


# ── start_at / due_at validation (PLAN.md §5) ────────────────────────────────


def test_task_dates_round_trip(service: ProjectService, project: Any, owner: Actor) -> None:
    task = service.create_task(
        project.id, user=owner, title="T", start_at=1_700_000_000, due_at=1_700_003_600
    )
    assert (task.start_at, task.due_at) == (1_700_000_000, 1_700_003_600)

    patched = service.update_task(project.id, task.id, user=owner, start_at=1_700_000_100)
    assert patched.start_at == 1_700_000_100
    assert service.update_task(project.id, task.id, user=owner, start_at=None).start_at is None


@pytest.mark.parametrize("bad", [0, -1, 4102444800, 1_700_000_000_000])
def test_out_of_range_task_dates_are_400(
    service: ProjectService, project: Any, owner: Actor, bad: int
) -> None:
    """The upper bound also catches the common milliseconds mix-up (~1.7e12)."""
    with pytest.raises(OctopError) as err:
        service.create_task(project.id, user=owner, title="T", start_at=bad)
    assert err.value.code is ErrorCode.PROJECT_TASK_DATE_INVALID
    assert err.value.status == 400
    assert err.value.status != 500


def test_start_after_due_is_400_on_create_and_patch(
    service: ProjectService, project: Any, owner: Actor
) -> None:
    with pytest.raises(OctopError) as err:
        service.create_task(
            project.id, user=owner, title="T", start_at=1_700_003_600, due_at=1_700_000_000
        )
    assert err.value.code is ErrorCode.PROJECT_TASK_DATE_INVALID
    assert err.value.status == 400

    task = service.create_task(project.id, user=owner, title="T", start_at=1_700_003_600)
    with pytest.raises(OctopError) as err:
        service.update_task(project.id, task.id, user=owner, due_at=1_700_000_000)
    assert err.value.code is ErrorCode.PROJECT_TASK_DATE_INVALID
    assert err.value.status == 400
    # The refused patch wrote nothing.
    assert service.get_task(project.id, task.id, user=owner).due_at is None


# ── project state machine (PLAN.md §3.1) ─────────────────────────────────────


def test_project_vocabulary_is_the_frozen_six():
    assert PROJECT_STATUSES == PROJECT_VOCABULARY


def test_project_transition_graph_shape():
    assert set(_TRANSITIONS) == set(PROJECT_STATUSES)
    for source, edges in _TRANSITIONS.items():
        assert edges <= set(PROJECT_STATUSES), source
    assert _TRANSITIONS["archived"] == frozenset()
    assert _TRANSITIONS["draft"] == frozenset({"active", "cancelled"})


def test_project_lifecycle_and_reopen(service: ProjectService, owner: Actor) -> None:
    project = service.create_project(owner_user=owner, name="Beta")
    assert project.status == "draft"

    active = service.transition_project(project.id, user=owner, target="active")
    assert active.status == "active"
    completed = service.transition_project(project.id, user=owner, target="completed")
    assert completed.status == "completed"
    reopened = service.transition_project(project.id, user=owner, target="active")
    assert reopened.status == "active"
    paused = service.transition_project(project.id, user=owner, target="paused")
    assert paused.status == "paused"
    cancelled = service.transition_project(project.id, user=owner, target="cancelled")
    assert cancelled.status == "cancelled"
    assert service.transition_project(project.id, user=owner, target="active").status == "active"


def test_draft_cannot_complete_directly(service: ProjectService, owner: Actor) -> None:
    project = service.create_project(owner_user=owner, name="Beta")

    with pytest.raises(OctopError) as err:
        service.transition_project(project.id, user=owner, target="completed")
    assert err.value.code is ErrorCode.PROJECT_STATUS_INVALID
    assert err.value.status == 409


def test_archived_is_terminal_and_read_only(service: ProjectService, owner: Actor) -> None:
    project = service.create_project(owner_user=owner, name="Beta")
    service.transition_project(project.id, user=owner, target="active")
    service.transition_project(project.id, user=owner, target="archived")

    # Read-only fires before the graph: any change to an archived project is a 403.
    with pytest.raises(OctopError) as err:
        service.transition_project(project.id, user=owner, target="active")
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
    assert _TRANSITIONS["archived"] == frozenset()

    # Read stays open; every write level is refused (the archived rule must not
    # have been relaxed while the graph grew).
    assert service.get_project(project.id, user=owner).status == "archived"
    with pytest.raises(OctopError) as err:
        service.create_task(project.id, user=owner, title="T")
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
    with pytest.raises(OctopError) as err:
        service.assert_project_role(project.id, user=owner, required=PROJECT_WRITE)
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN


# ── creation-time status is an assignment, not a transition (SPEC S-10) ──────


@pytest.mark.parametrize("target", PROJECT_VOCABULARY)
def test_project_can_be_created_directly_in_every_state(
    service: ProjectService, owner: Actor, target: str
) -> None:
    """The creation dialog offers all six states; ``_TRANSITIONS`` must not gate it."""
    project = service.create_project(owner_user=owner, name=f"P-{target}", status=target)
    assert project.status == target


def test_project_create_defaults_to_draft(service: ProjectService, owner: Actor) -> None:
    assert service.create_project(owner_user=owner, name="Gamma").status == "draft"


def test_unknown_project_status_at_creation_is_a_409_not_a_500(
    service: ProjectService, owner: Actor
) -> None:
    with pytest.raises(OctopError) as err:
        service.create_project(owner_user=owner, name="Gamma", status="bogus")
    assert err.value.code is ErrorCode.PROJECT_STATUS_INVALID
    assert err.value.status == 409
    assert err.value.status != 500
