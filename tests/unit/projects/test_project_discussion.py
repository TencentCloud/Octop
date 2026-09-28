"""Project discussion line — plan T3.1, covering AC-03 and AC-04.

AC-03 is the isolation property: a task's discussion line holds exactly its own
comments, so nothing leaks from one task to another. AC-04 is the attribution
contract: every row carries ``author_type`` / ``author_id`` / ``created_at``, and
an agent-authored row is marked ``source='agent'``.

Permission cases are driven through the reused :class:`ProjectService` checks, so
a rejected write must leave no row behind.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.project_content import (
    COMMENT_AUTHOR_AGENT,
    COMMENT_AUTHOR_USER,
    COMMENT_SOURCE_AGENT,
    COMMENT_SOURCE_DASHBOARD,
    ProjectCommentRepo,
)
from octop.infra.db.repos.project_tasks import ProjectTaskRepo, TimelineRepo
from octop.infra.db.repos.projects import MEMBER_SUBJECT_USER, ProjectMemberRepo, ProjectRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge import service as knowledge_service_module
from octop.infra.projects import service as project_service_module
from octop.infra.projects.discussion import ProjectDiscussion
from octop.infra.projects.service import ProjectService
from octop.infra.utils.paths import PathLayout


class Actor:
    """Minimal user stand-in: ``id`` + ``is_admin`` + ``permissions``."""

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
    # The knowledge feature gate needs an embedding provider; project creation is
    # the fixture's setup step, not what this file tests.
    monkeypatch.setattr(knowledge_service_module, "assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(
        project_service_module, "get_capability", lambda *_a, **_k: {"usable": True}
    )
    return SimpleNamespace(
        db=pool,
        project_repo=ProjectRepo(pool),
        project_member_repo=ProjectMemberRepo(pool),
        project_task_repo=ProjectTaskRepo(pool),
        project_comment_repo=ProjectCommentRepo(pool),
        timeline_repo=TimelineRepo(pool),
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
        paths=PathLayout.from_env(),
    )


@pytest.fixture
def service(services: SimpleNamespace) -> ProjectService:
    return ProjectService(services)


@pytest.fixture
def discussion(services: SimpleNamespace) -> ProjectDiscussion:
    return ProjectDiscussion(services)


@pytest.fixture
def owner(services: SimpleNamespace) -> Actor:
    return Actor(services.user_repo.create(username="owner", password_hash="h", role="user"))


@pytest.fixture
def project(service: ProjectService, owner: Actor) -> Any:
    return service.create_project(owner_user=owner, name="Alpha")


def add_member(
    service: ProjectService,
    project_id: str,
    *,
    actor: Actor,
    subject_id: str,
    role: str,
) -> None:
    service.add_member(
        project_id,
        user=actor,
        subject_type=MEMBER_SUBJECT_USER,
        subject_id=subject_id,
        role=role,
        subject_user_id=int(subject_id),
    )


# ── AC-03: a task's line holds exactly its own comments ──────────────────────


def test_each_task_reads_back_only_its_own_three_comments(
    service: ProjectService, discussion: ProjectDiscussion, owner: Actor, project: Any
) -> None:
    first = service.create_task(project.id, user=owner, title="Task A")
    second = service.create_task(project.id, user=owner, title="Task B")
    for index in range(3):
        discussion.add_comment(project.id, user=owner, task_id=first.id, body=f"A{index}")
        discussion.add_comment(project.id, user=owner, task_id=second.id, body=f"B{index}")

    first_line = discussion.list_comments(project.id, user=owner, task_id=first.id)
    second_line = discussion.list_comments(project.id, user=owner, task_id=second.id)

    assert [c.body for c in first_line] == ["A0", "A1", "A2"]
    assert [c.body for c in second_line] == ["B0", "B1", "B2"]
    assert {c.task_id for c in first_line} == {first.id}
    assert {c.task_id for c in second_line} == {second.id}
    assert discussion.count_for_task(project.id, first.id) == 3
    assert discussion.count_for_task(project.id, second.id) == 3
    # The project-wide line still sees both tasks' comments.
    assert len(discussion.list_comments(project.id, user=owner)) == 6


def test_lines_are_chronological_oldest_first(
    service: ProjectService, discussion: ProjectDiscussion, owner: Actor, project: Any
) -> None:
    first = service.create_task(project.id, user=owner, title="Task A")
    second = service.create_task(project.id, user=owner, title="Task B")

    discussion.add_comment(project.id, user=owner, body="project level")
    # A comment with no task_id belongs to the project line, not to any task.
    assert discussion.list_comments(project.id, user=owner, task_id=first.id) == []

    discussion.add_comment(project.id, user=owner, task_id=first.id, body="on A")
    discussion.add_comment(project.id, user=owner, task_id=second.id, body="on B")

    project_line = discussion.list_comments(project.id, user=owner)
    assert [c.body for c in project_line] == ["project level", "on A", "on B"]
    assert project_line[0].task_id is None
    assert [
        c.body for c in discussion.list_comments(project.id, user=owner, task_id=second.id)
    ] == ["on B"]
    assert discussion.count_for_task(project.id, second.id) == 1


# ── AC-04: every comment records who wrote it ────────────────────────────────


def test_human_comment_records_its_author_and_timestamp(
    service: ProjectService, discussion: ProjectDiscussion, owner: Actor, project: Any
) -> None:
    task = service.create_task(project.id, user=owner, title="Task A")

    row = discussion.add_comment(project.id, user=owner, task_id=task.id, body="人手评论")

    assert row.author_type == COMMENT_AUTHOR_USER
    assert row.author_id == str(owner.id)
    assert row.source == COMMENT_SOURCE_DASHBOARD
    assert row.created_at > 0
    assert row.updated_at == row.created_at, "a fresh comment has never been updated"
    assert row.body == "人手评论"

    (stored,) = discussion.list_comments(project.id, user=owner, task_id=task.id)
    assert (stored.author_type, stored.author_id, stored.created_at) == (
        COMMENT_AUTHOR_USER,
        str(owner.id),
        row.created_at,
    )


def test_agent_comment_records_author_type_and_agent_source(
    service: ProjectService, discussion: ProjectDiscussion, owner: Actor, project: Any
) -> None:
    task = service.create_task(project.id, user=owner, title="Task A")

    row = discussion.add_agent_comment(
        project.id,
        user=owner,
        agent_id="agent-7",
        task_id=task.id,
        thread_id="th_agent",
        body="expert output",
    )

    assert row.author_type == COMMENT_AUTHOR_AGENT
    assert row.author_id == "agent-7"
    assert row.source == COMMENT_SOURCE_AGENT
    assert row.task_id == task.id
    assert row.thread_id == "th_agent"
    assert row.created_at > 0
    # The dashboard path keeps its own source on the same line.
    human = discussion.add_comment(project.id, user=owner, task_id=task.id, body="thanks")
    assert human.source == COMMENT_SOURCE_DASHBOARD


# ── rejected writes leave no row ─────────────────────────────────────────────


@pytest.mark.parametrize("body", ["", "   ", "\n\t"])
def test_blank_body_is_rejected(
    discussion: ProjectDiscussion, owner: Actor, project: Any, body: str
) -> None:
    with pytest.raises(ValueError, match="comment body is required"):
        discussion.add_comment(project.id, user=owner, body=body)
    assert discussion.list_comments(project.id, user=owner) == []


def test_unknown_author_type_is_rejected(
    discussion: ProjectDiscussion, owner: Actor, project: Any
) -> None:
    with pytest.raises(ValueError, match="unknown comment author_type"):
        discussion.add_comment(project.id, user=owner, body="hi", author_type="robot")
    assert discussion.list_comments(project.id, user=owner) == []


def test_agent_author_must_name_its_author_id(
    discussion: ProjectDiscussion, owner: Actor, project: Any
) -> None:
    with pytest.raises(ValueError, match="must name its author_id"):
        discussion.add_comment(project.id, user=owner, body="hi", author_type=COMMENT_AUTHOR_AGENT)


def test_unknown_task_is_rejected(
    discussion: ProjectDiscussion, owner: Actor, project: Any
) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        discussion.add_comment(project.id, user=owner, task_id="nope", body="orphan")
    assert discussion.list_comments(project.id, user=owner) == []


def test_task_from_another_project_is_rejected(
    service: ProjectService, discussion: ProjectDiscussion, owner: Actor, project: Any
) -> None:
    other = service.create_project(owner_user=owner, name="Beta")
    foreign = service.create_task(other.id, user=owner, title="elsewhere")

    with pytest.raises(ValueError, match="belongs to another project"):
        discussion.add_comment(project.id, user=owner, task_id=foreign.id, body="wrong project")
    assert discussion.list_comments(project.id, user=owner) == []

    # The same task is fine on its own project's line: the pair is what is checked.
    mine = discussion.add_comment(other.id, user=owner, task_id=foreign.id, body="right project")
    assert mine.task_id == foreign.id


# ── permissions (§4.6, reused from ProjectService) ───────────────────────────


def test_non_member_is_forbidden_even_when_a_platform_admin(
    services: SimpleNamespace, discussion: ProjectDiscussion, owner: Actor, project: Any
) -> None:
    outsider = Actor(
        services.user_repo.create(username="outsider", password_hash="h", role="admin"), admin=True
    )

    with pytest.raises(OctopError) as err:
        discussion.add_comment(project.id, user=outsider, body="let me in")
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN

    with pytest.raises(OctopError) as err:
        discussion.list_comments(project.id, user=outsider)
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN


def test_viewer_can_read_but_not_comment(
    service: ProjectService, discussion: ProjectDiscussion, owner: Actor, project: Any
) -> None:
    viewer = Actor(owner.id + 100)
    add_member(service, project.id, actor=owner, subject_id=str(viewer.id), role="viewer")
    existing = discussion.add_comment(project.id, user=owner, body="owner wrote this")

    assert [c.id for c in discussion.list_comments(project.id, user=viewer)] == [existing.id]

    with pytest.raises(OctopError) as err:
        discussion.add_comment(project.id, user=viewer, body="viewer tries to write")
    assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN
    assert [c.id for c in discussion.list_comments(project.id, user=owner)] == [existing.id]


# ── project scoping and cascade ──────────────────────────────────────────────


def test_comments_are_project_scoped_and_cascade_on_project_delete(
    service: ProjectService,
    services: SimpleNamespace,
    discussion: ProjectDiscussion,
    owner: Actor,
    project: Any,
) -> None:
    other = service.create_project(owner_user=owner, name="Beta")
    task = service.create_task(project.id, user=owner, title="Task A")
    mine = discussion.add_comment(project.id, user=owner, task_id=task.id, body="here")
    theirs = discussion.add_comment(other.id, user=owner, body="there")

    assert [c.id for c in discussion.list_comments(project.id, user=owner)] == [mine.id]
    assert [c.id for c in discussion.list_comments(other.id, user=owner)] == [theirs.id]

    assert service.delete_project(project.id, user=owner) is True

    assert services.project_comment_repo.get(mine.id) is None, "child rows cascade"
    assert services.project_comment_repo.get(theirs.id) is not None
