"""Y1「与我相关」/ Y2「成员动态（按人筛选）」—— service 层的合成语义。

判据口径（PLAN §9 / `LEARNINGS §20.22`）：凡"遍历 X 并检查 X 的成员"的形态，
**先断言 X 非空** —— 空集必须报错，而不是静默通过。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.audit import AuditRepo
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.project_artifacts import ProjectArtifactRepo
from octop.infra.db.repos.project_content import ProjectCommentRepo
from octop.infra.db.repos.project_tasks import ProjectTaskRepo, TimelineRepo
from octop.infra.db.repos.projects import ProjectMemberRepo, ProjectRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.knowledge import service as knowledge_service_module
from octop.infra.projects import service as project_service_module
from octop.infra.projects.discussion import ProjectDiscussion
from octop.infra.projects.service import ProjectService
from octop.infra.utils.paths import PathLayout


class Actor:
    def __init__(self, user_id: int, *, admin: bool = False) -> None:
        self.id = user_id
        self._admin = admin
        self.permissions = ["projects", "knowledge_bases"]

    @property
    def is_admin(self) -> bool:
        return self._admin


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    monkeypatch.setattr(knowledge_service_module, "assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(
        project_service_module, "get_capability", lambda *_a, **_k: {"usable": True}
    )
    services = SimpleNamespace(
        db=pool,
        project_repo=ProjectRepo(pool),
        project_member_repo=ProjectMemberRepo(pool),
        project_task_repo=ProjectTaskRepo(pool),
        timeline_repo=TimelineRepo(pool),
        project_comment_repo=ProjectCommentRepo(pool),
        project_artifact_repo=ProjectArtifactRepo(pool),
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
        agent_repo=AgentRepo(pool),
        thread_repo=ThreadRepo(pool),
        audit_repo=AuditRepo(pool),
        paths=PathLayout.from_env(),
    )
    service = ProjectService(services)
    owner = Actor(services.user_repo.create(username="owner", password_hash="h", role="user"))
    other = Actor(services.user_repo.create(username="other", password_hash="h", role="user"))
    project = service.create_project(owner_user=owner, name="Feed project")
    for actor in (other,):
        service.add_member(
            project.id,
            user=owner,
            subject_type="user",
            subject_id=str(actor.id),
            role="member",
            subject_user_id=actor.id,
        )
    services.project = project
    services.owner = owner
    services.other = other
    services.service = service
    services.discussion = ProjectDiscussion(services)
    return services


def _task(env: SimpleNamespace, *, title: str, assignee: Actor | None, assignee_type: str = "user"):
    fields = {"assignee_type": assignee_type, "assignee_id": str(assignee.id)} if assignee else {}
    return env.service.create_task(env.project.id, user=env.owner, title=title, **fields)


def _comment(
    env: SimpleNamespace,
    *,
    body: str,
    author: Actor,
    task_id: str | None = None,
    mentions: list[dict[str, str]] | None = None,
):
    return env.project_comment_repo.create(
        project_id=env.project.id,
        author_type="user",
        author_id=str(author.id),
        body=body,
        task_id=task_id,
        mentions=mentions,
    )


def test_y1_relevance_is_a_member_of_the_full_feed(env: SimpleNamespace) -> None:
    """Y1 ⊆ feed, and the two inclusion rules are both exercised.

    The precondition assertion is deliberate (`LEARNINGS §20.22`): a filter test
    that iterates an empty feed would pass without checking anything.
    """
    mine = _task(env, title="mine", assignee=env.owner)
    theirs = _task(env, title="theirs", assignee=env.other)

    mentioned = _comment(
        env,
        body="hey @owner",
        author=env.other,
        mentions=[{"type": "user", "id": str(env.owner.id)}],
    )
    on_my_task = _comment(env, body="on my task", author=env.other, task_id=mine.id)
    on_their_task = _comment(env, body="their business", author=env.other, task_id=theirs.id)
    project_level = _comment(env, body="project level", author=env.other)
    someone_else_mentioned = _comment(
        env,
        body="hey @other",
        author=env.owner,
        mentions=[{"type": "user", "id": str(env.other.id)}],
    )

    feed = env.discussion.list_comments(env.project.id, user=env.owner)
    assert len(feed) == 5, "the precondition: the feed must not be empty"
    relevant = env.discussion.list_comments(env.project.id, user=env.owner, relevant_to=env.owner)

    ids = {row.id for row in relevant}
    assert ids == {mentioned.id, on_my_task.id}, ids
    assert ids <= {row.id for row in feed}, "Y1 must be a subset of the feed"
    assert on_their_task.id not in ids, "a task assigned to somebody else is not relevant"
    assert project_level.id not in ids, "a comment with no task is never task-relevant"
    assert someone_else_mentioned.id not in ids, "a mention of somebody else is not mine"


def test_y1_ignores_a_task_assigned_to_another_subject_type(env: SimpleNamespace) -> None:
    """The assignee is a two-column pair: the same id under ``agent`` is not me."""
    mine = _task(env, title="mine", assignee=env.owner)
    agent_side = _task(env, title="agent side", assignee=env.owner, assignee_type="agent")

    on_mine = _comment(env, body="mine", author=env.other, task_id=mine.id)
    on_agent = _comment(env, body="agent task", author=env.other, task_id=agent_side.id)

    relevant = env.discussion.list_comments(env.project.id, user=env.owner, relevant_to=env.owner)
    ids = {row.id for row in relevant}
    assert len(ids) == 1, "the precondition: exactly one relevant row"
    assert ids == {on_mine.id}
    assert on_agent.id not in ids


def test_y1_tolerates_a_malformed_mentions_payload(env: SimpleNamespace) -> None:
    """A bad stored payload must not break the feed (it simply matches nobody)."""
    broken = _comment(env, body="broken", author=env.other, mentions=None)
    with env.db.transaction() as conn:
        conn.execute(
            "UPDATE project_comments SET mentions = ? WHERE comment_id = ?",
            ("{not json", broken.id),
        )
    assert env.discussion.list_comments(env.project.id, user=env.owner, relevant_to=env.owner) == []


def test_y2_author_filter_is_a_subset_and_needs_both_columns(env: SimpleNamespace) -> None:
    mine = _comment(env, body="by me", author=env.owner)
    theirs = _comment(env, body="by other", author=env.other)

    feed = env.discussion.list_comments(env.project.id, user=env.owner)
    assert len(feed) == 2, "the precondition: two rows to filter from"
    only_mine = env.discussion.list_comments(
        env.project.id,
        user=env.owner,
        author_id=str(env.owner.id),
        author_type="user",
    )
    assert {row.id for row in only_mine} == {mine.id}
    assert {row.id for row in only_mine} <= {row.id for row in feed}, "Y2 ⊆ feed"
    assert theirs.id not in {row.id for row in only_mine}

    with pytest.raises(ValueError):
        env.discussion.list_comments(env.project.id, user=env.owner, author_id=str(env.owner.id))


def test_y1_never_matches_on_the_body_text(env: SimpleNamespace) -> None:
    """The discriminating property of this batch: the **body** is never parsed.

    A comment that merely *names* a real user in its text, with no structured
    ``mentions``, must not become "relevant to" them. Design P1 = (c): the
    dashboard submits structured ids and the server only stores them.

    The control assertion matters as much as the first one: without it, "absent
    from the result" could also mean "the row was never created".
    """
    bait = _comment(env, body="please let owner take a look", author=env.other)
    assert bait.mentions is None, "the bait must carry no structured mentions"

    feed = env.discussion.list_comments(env.project.id, user=env.owner)
    assert len(feed) >= 1, "precondition: the feed must not be empty (§20.22)"
    assert bait.id in {row.id for row in feed}, "control: the bait exists in the feed"

    relevant = env.discussion.list_comments(env.project.id, user=env.owner, relevant_to=env.owner)
    assert bait.id not in {row.id for row in relevant}, (
        "naming a user in the body must not make a comment relevant: the server "
        "stores structured mentions and never parses the text"
    )
