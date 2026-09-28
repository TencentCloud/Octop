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
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.audit import AuditRepo
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.project_content import (
    COMMENT_AUTHOR_AGENT,
    COMMENT_AUTHOR_USER,
    COMMENT_NODE_CONCLUSION,
    COMMENT_NODE_NONE,
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
        agent_repo=AgentRepo(pool),
        audit_repo=AuditRepo(pool),
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


# ── batch 8 (T-B8-API): conclusion marker + concluded filter ─────────────────
#
# Only additions: the comment store, its service and the permission checks are the
# ones already covered above; this covers the one new value the batch introduces.


def test_conclusion_mark_is_idempotent_and_filterable(
    discussion: ProjectDiscussion,
    service: ProjectService,
    project: Any,
    owner: Actor,
) -> None:
    first = discussion.add_comment(project.id, user=owner, body="first")
    second = discussion.add_comment(project.id, user=owner, body="second")

    # Not adopted yet: everything is on the "not concluded" side.
    assert [c.id for c in discussion.list_comments(project.id, user=owner, concluded=True)] == []
    assert len(discussion.list_comments(project.id, user=owner, concluded=False)) == 2

    marked = discussion.set_conclusion(project.id, second.id, user=owner, concluded=True)
    assert marked.id == second.id
    assert marked.node_type == COMMENT_NODE_CONCLUSION

    # Idempotent: adopting twice keeps exactly one conclusion and one value.
    again = discussion.set_conclusion(project.id, second.id, user=owner, concluded=True)
    assert again.node_type == COMMENT_NODE_CONCLUSION
    concluded = discussion.list_comments(project.id, user=owner, concluded=True)
    assert [c.id for c in concluded] == [second.id]
    assert [c.id for c in discussion.list_comments(project.id, user=owner, concluded=False)] == [
        first.id
    ]

    # Un-adopting is idempotent too, and the default (no filter) still sees both.
    for _ in range(2):
        cleared = discussion.set_conclusion(project.id, second.id, user=owner, concluded=False)
        assert cleared.node_type == COMMENT_NODE_NONE
    assert len(discussion.list_comments(project.id, user=owner)) == 2
    assert discussion.list_comments(project.id, user=owner, concluded=True) == []


def test_conclusion_of_a_foreign_comment_is_a_404(
    discussion: ProjectDiscussion,
    service: ProjectService,
    project: Any,
    owner: Actor,
    services: SimpleNamespace,
) -> None:
    """A comment id from another project is "not in this project", not a 500."""
    other = service.create_project(owner_user=owner, name="Borealis")
    foreign = discussion.add_comment(other.id, user=owner, body="elsewhere")

    with pytest.raises(OctopError) as err:
        discussion.set_conclusion(project.id, foreign.id, user=owner, concluded=True)
    assert err.value.code is ErrorCode.PROJECT_NOT_FOUND
    assert err.value.status == 404
    assert err.value.status != 500
    assert discussion.list_comments(other.id, user=owner, concluded=True) == []


# ── batch 8 FIND-1: the resolved display names are asserted, not just produced ─
#
# The wire models carry ``CommentOut.name`` / ``TimelineEventOut.actor_name``. Both
# come from ``ProjectService.resolve_actor_name`` → ``_resolve_subject_name``. These
# run the same real service + real SQLite pool the endpoints use (no mocked
# resolver): pinning the resolver to ``None`` — the exact shape of the reported
# "row shows user:1" defect — turns these assertions red.


def test_comment_and_timeline_names_resolve_from_real_rows(
    discussion: ProjectDiscussion,
    service: ProjectService,
    project: Any,
    owner: Actor,
    services: SimpleNamespace,
) -> None:
    from octop.api.routers.projects import CommentOut, TimelineEventOut

    # ① a user author resolves to its username (display_name is unset here)
    comment = discussion.add_comment(project.id, user=owner, body="hello")
    resolved = service.resolve_actor_name(comment.author_type, comment.author_id)
    assert resolved == "owner", f"user comment author: {resolved!r}"
    assert CommentOut.of(comment, resolved).name == "owner"

    # ③ an agent author resolves through agents.name — the same read path
    services.agent_repo.create(
        agent_id="AGNAME1", user_id=owner.id, name="AI 编程实战导师", kind="expert"
    )
    agent_comment = discussion.add_agent_comment(
        project.id, user=owner, agent_id="AGNAME1", body="agent says hi"
    )
    agent_name = service.resolve_actor_name(agent_comment.author_type, agent_comment.author_id)
    assert agent_name == "AI 编程实战导师", agent_name
    assert CommentOut.of(agent_comment, agent_name).name == "AI 编程实战导师"

    # ② the timeline keeps the stable ``type:id`` actor **and** gains the name.
    # A task creation is what writes the first event on a fresh project.
    service.create_task(project.id, user=owner, title="Named timeline task")
    events = service.list_timeline(project.id, user=owner)
    assert events, "a freshly created project has at least one event"
    for row in events:
        model = TimelineEventOut.of(row, service.resolve_actor_ref_name(row.actor))
        assert model.actor == row.actor, "actor keeps its existing stable format"
        assert ":" in model.actor and not model.actor.startswith(":")
        assert model.actor_name == "owner", (row.actor, model.actor_name)

    # an unresolvable actor is null, never an exception
    assert service.resolve_actor_ref_name("user:999999") is None
    assert service.resolve_actor_name("agent", "ag_missing") is None


# ── batch 9 (T-19-API): the two columns, the audit log, and their transaction ─


def _audit_rows(services: SimpleNamespace, comment_id: str) -> list[str]:
    with services.db.connect() as conn:
        rows = conn.execute(
            "SELECT action FROM audit_log WHERE target = ? ORDER BY ts, id", (comment_id,)
        ).fetchall()
    return [str(r["action"]) for r in rows]


def test_conclusion_writes_the_actor_columns_and_logs_both_actions(
    discussion: ProjectDiscussion,
    services: SimpleNamespace,
    project: Any,
    owner: Actor,
) -> None:
    """Adopting stores the actor; un-adopting clears it — and both land in audit."""
    owner.username = "owner"  # audit records the username, like every other writer
    comment = discussion.add_comment(project.id, user=owner, body="adopt me")

    adopted = discussion.set_conclusion(project.id, comment.id, user=owner, concluded=True)
    assert adopted.concluded_by_type == "user"
    assert adopted.concluded_by_id == str(owner.id)

    cleared = discussion.set_conclusion(project.id, comment.id, user=owner, concluded=False)
    assert cleared.concluded_by_type is None and cleared.concluded_by_id is None

    assert _audit_rows(services, comment.id) == [
        "project.comment.conclude",
        "project.comment.unconclude",
    ]


def test_a_failed_audit_write_rolls_the_state_back(
    discussion: ProjectDiscussion,
    services: SimpleNamespace,
    project: Any,
    owner: Actor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PLAN.md §2.1c P6: state and audit share one transaction.

    The probe replaces ``audit.write`` with a raising call — the real code path,
    only the failure injected — and then reads the row back from the database.
    """
    comment = discussion.add_comment(project.id, user=owner, body="roll me back")
    before = services.project_comment_repo.get(comment.id)
    assert before is not None and before.node_type == COMMENT_NODE_NONE

    def _boom(**_kwargs: Any) -> None:
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(discussion._audit, "write", _boom)

    with pytest.raises(RuntimeError):
        discussion.set_conclusion(project.id, comment.id, user=owner, concluded=True)

    after = services.project_comment_repo.get(comment.id)
    assert after is not None
    assert after.node_type == COMMENT_NODE_NONE, "state must roll back with the audit write"
    assert after.concluded_by_type is None and after.concluded_by_id is None
    assert _audit_rows(services, comment.id) == []


def test_a_half_pair_of_conclusion_columns_is_rejected(
    services: SimpleNamespace, discussion: ProjectDiscussion, project: Any, owner: Actor
) -> None:
    """FIND-4: the two actor columns are set together or not at all.

    Repo-layer guarantee (the only writer is ``set_node_type``); see the method's
    comment for the stated boundary — raw SQL is not constrained (SQLite cannot add
    a CHECK via ALTER TABLE).
    """
    comment = discussion.add_comment(project.id, user=owner, body="half pair")
    repo = services.project_comment_repo

    with pytest.raises(ValueError):
        repo.set_node_type(comment.id, COMMENT_NODE_CONCLUSION, concluded_by_type="user")
    with pytest.raises(ValueError):
        repo.set_node_type(comment.id, COMMENT_NODE_CONCLUSION, concluded_by_id=str(owner.id))

    # Nothing was written by the rejected calls, and the pair path still works.
    after = repo.get(comment.id)
    assert after is not None and after.node_type == COMMENT_NODE_NONE
    assert after.concluded_by_type is None and after.concluded_by_id is None
    assert repo.set_node_type(
        comment.id,
        COMMENT_NODE_CONCLUSION,
        concluded_by_type="user",
        concluded_by_id=str(owner.id),
    )
    paired = repo.get(comment.id)
    assert paired is not None
    assert (paired.concluded_by_type, paired.concluded_by_id) == ("user", str(owner.id))


def test_the_read_face_uses_the_columns_not_the_audit_log(
    discussion: ProjectDiscussion,
    services: SimpleNamespace,
    project: Any,
    owner: Actor,
) -> None:
    """FIND-L3: the columns are the authority; ``audit_log`` is only history.

    A literal "log and column disagree, trust the column" case would be tautological
    — nothing in the read path ever looks at ``audit_log``. So this builds a **half
    state** instead: the columns are written straight through the repo (bypassing
    ``set_conclusion``) and **no audit row exists at all**. A read face that derived
    "concluded" from ``audit_log`` would report nothing here and go red.

    Boundary: some requirements have no runtime counter-example at all (a "no second
    permission system" style structural absence). Those are covered by static
    criteria plus a negative grep — never by a fabricated runtime case, because a
    tautological test reads as coverage while proving nothing.
    """
    from octop.infra.db.repos.project_content import COMMENT_NODE_CONCLUSION as CONCLUSION

    comment = discussion.add_comment(project.id, user=owner, body="columns only")
    with services.db.transaction() as conn:
        services.project_comment_repo.set_node_type(
            comment.id,
            CONCLUSION,
            concluded_by_type="user",
            concluded_by_id=str(owner.id),
            conn=conn,
        )

    with services.db.connect() as conn:
        audit_rows = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM audit_log WHERE target = ?", (comment.id,)
            ).fetchone()["c"]
        )
    assert audit_rows == 0, "the half state must have no audit trail at all"

    listed = discussion.list_comments(project.id, user=owner, concluded=True)
    assert [row.id for row in listed] == [comment.id]
    assert listed[0].node_type == CONCLUSION
    assert listed[0].concluded_by_id == str(owner.id)
