"""Project task dispatch (plan §T2.5) — prompt assembly, validation, thread binding.

**The real agent turn is NOT covered here.** This machine has no LLM provider and
no configured agent, so nothing in this file runs a harness turn: the agent
registry is stubbed (:class:`_StubAgentManager`) and every assertion is about what
the dispatch path *asks* it to do — which agent id streams, with which request.
Whether a team host's ``ask_agent`` really opens the room and fans member speech
back is therefore **unverified**; that needs a live provider and a real team.

What is covered, with a real SQLite control plane:

* the dispatched prompt text (AC-09) — pure, no runtime;
* rejected inputs (assignee type, missing task, foreign project, non-member);
* assignee state errors (``AGENT_NOT_FOUND`` / ``AGENT_NOT_RUNNING``);
* the happy path: thread created, ``project_tasks.thread_id`` written,
  ``task.dispatched`` timeline row, prompt projected as the thread's first message;
* the team branch stamping the team host runtime (step ④) instead of running the
  assignee as a plain expert.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.routing import Match

from octop.api.routers.projects import router as projects_router
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.project_tasks import (
    TIMELINE_TASK_CREATED,
    TIMELINE_TASK_DISPATCHED,
    ProjectTaskRepo,
    TimelineRepo,
    actor_ref,
)
from octop.infra.db.repos.projects import MEMBER_SUBJECT_USER, ProjectMemberRepo, ProjectRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.usage import UsageRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.projects.dispatch import (
    DISPATCH_CHAT_TYPE,
    build_dispatch_prompt,
    dispatch_session_key,
    require_dispatch_session_key,
    run_dispatch_turn,
    split_acceptance,
    task_link,
)
from octop.infra.projects.service import ProjectService

EXPERT_ID = "ag-expert"
TEAM_ID = "ag-team"
REPLY = "收到，我来处理。"
DESCRIPTION = "把看板拖拽做完。\n\n## 验收标准\n- 拖拽后状态列立即更新\n- 刷新后状态保持"

EXPECTED_PROMPT = (
    "【项目派工】Alpha\n"
    "\n"
    "## 任务标题\n"
    "看板拖拽\n"
    "\n"
    "## 任务描述\n"
    "把看板拖拽做完。\n"
    "\n"
    "## 验收标准\n"
    "- 拖拽后状态列立即更新\n"
    "- 刷新后状态保持\n"
    "\n"
    "任务链接：/projects/{project_id}?task={task_id}"
)


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


class _StubAgentManager:
    """Agent registry stand-in — no harness, no provider, no turn.

    Mirrors the two behaviours the dispatch path relies on: ``get_agent`` raising
    the registry's own ``AGENT_NOT_FOUND`` / ``AGENT_NOT_RUNNING``, and ``stream``
    yielding the chunks ``run_agent_turn`` consumes.
    """

    def __init__(
        self,
        *,
        kinds: dict[str, str],
        running: set[str],
        reply: str = REPLY,
        failure: Exception | None = None,
    ) -> None:
        self.kinds = kinds
        self.running = running
        self.reply = reply
        self.failure = failure
        self.streams: list[tuple[str, dict[str, Any]]] = []

    def get_row(self, agent_id: str) -> Any | None:
        kind = self.kinds.get(agent_id)
        if kind is None:
            return None
        return SimpleNamespace(agent_id=agent_id, name=agent_id, kind=kind, default_model=None)

    def get_agent(self, agent_id: str) -> Any:
        row = self.get_row(agent_id)
        if row is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
        if agent_id not in self.running:
            raise OctopError(ErrorCode.AGENT_NOT_RUNNING, f"agent {agent_id!r} not running")
        return SimpleNamespace(agent_id=agent_id)

    def default_mcp_servers(self, agent_id: str) -> list[str]:
        return []

    def merge_turn_mcp_servers(
        self,
        user_id: int,
        explicit: list[str] | None,
        *,
        apply_defaults: bool = True,
        extra_defaults: list[str] | None = None,
    ) -> list[str]:
        return []

    async def prepare_chat_mcp(
        self, agent_id: str, servers: list[str], *, connector_user_id: int | None = None
    ) -> list[str]:
        return []

    def default_knowledge_base_ids(self, agent_id: str) -> list[str]:
        return []

    async def stream(self, agent_id: str, request: dict[str, Any]) -> Any:
        self.streams.append((agent_id, request))
        if self.failure is not None:
            raise self.failure
        yield {"type": "token", "content": self.reply}


class _StubTeams:
    """Records the team-room calls the R17 bridge makes."""

    def __init__(self) -> None:
        self.stamped: list[tuple[dict[str, Any], str]] = []

    def stamp_host_runtime(self, request: dict[str, Any], agent_id: str) -> None:
        self.stamped.append((request, agent_id))


class _StubGateway:
    """Gateway stand-in: a real :class:`ThreadRegistry` over the test database.

    ``require_session`` / ``run_in_session`` mirror the real ones (the lock is
    in-process here), so thread creation and session rebinding are exercised for
    real instead of being mocked away.
    """

    def __init__(self, services: SimpleNamespace) -> None:
        self._sessions = services.session_repo
        self.thread_registry = ThreadRegistry(
            session_repo=services.session_repo,
            thread_repo=services.thread_repo,
        )
        self.teams = _StubTeams()
        self.processor = SimpleNamespace(teams=self.teams)
        self.locked: list[tuple[str, str]] = []

    def require_session(self, agent_id: str, session_key: str) -> Any:
        session = self._sessions.get(session_key)
        if session is None:
            raise ValueError(f"session {session_key!r} not found")
        if session.agent_id != agent_id:
            raise ValueError(f"session {session_key!r} does not belong to agent {agent_id!r}")
        return session

    async def run_in_session(self, agent_id: str, session_key: str, operation: Any) -> None:
        self.locked.append((agent_id, session_key))
        await operation()


@pytest.fixture
def services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    # Real repos throughout: an empty DB leaves the knowledge feature unusable, so
    # `create_project` skips the KB — dispatch does not depend on one.
    user_repo = UserRepo(pool)
    knowledge_repo = KnowledgeRepo(pool)
    usage_repo = UsageRepo(pool)
    thread_message_repo = ThreadMessageRepo(pool)
    session_repo = SessionRepo(pool)
    return SimpleNamespace(
        db=pool,
        project_repo=ProjectRepo(pool),
        project_member_repo=ProjectMemberRepo(pool),
        project_task_repo=ProjectTaskRepo(pool),
        timeline_repo=TimelineRepo(pool),
        knowledge_repo=knowledge_repo,
        settings_repo=SettingsRepo(pool),
        user_repo=user_repo,
        agent_repo=AgentRepo(pool),
        thread_repo=ThreadRepo(pool),
        session_repo=session_repo,
        thread_message_repo=thread_message_repo,
        usage_repo=usage_repo,
        # The slice of ``RepoBundle`` the shared cron turn path reads, plus the
        # session repo the dispatch path creates its own dispatch session with.
        repos=SimpleNamespace(
            user_repo=user_repo,
            knowledge_repo=knowledge_repo,
            usage_repo=usage_repo,
            thread_message_repo=thread_message_repo,
            session_repo=session_repo,
        ),
    )


@pytest.fixture
def owner(services: SimpleNamespace) -> Actor:
    return Actor(services.user_repo.create(username="owner", password_hash="h", role="user"))


@pytest.fixture
def project(services: SimpleNamespace, owner: Actor) -> Any:
    return ProjectService(services).create_project(owner_user=owner, name="Alpha")


def build(
    services: SimpleNamespace,
    *,
    kinds: dict[str, str] | None = None,
    running: set[str] | None = None,
    failure: Exception | None = None,
) -> tuple[ProjectService, _StubAgentManager, _StubGateway]:
    """ProjectService wired to a stubbed registry and a real thread registry."""
    manager = _StubAgentManager(
        kinds=kinds if kinds is not None else {EXPERT_ID: "expert", TEAM_ID: "team"},
        running=running if running is not None else {EXPERT_ID, TEAM_ID},
        failure=failure,
    )
    gateway = _StubGateway(services)
    service = ProjectService(services, agent_manager=manager, gateway=gateway)  # type: ignore[arg-type]
    return service, manager, gateway


def make_task(
    service: ProjectService,
    project: Any,
    owner: Actor,
    *,
    assignee_type: str | None = "agent",
    assignee_id: str | None = EXPERT_ID,
    description: str = DESCRIPTION,
) -> Any:
    return service.create_task(
        project.id,
        user=owner,
        title="看板拖拽",
        description=description,
        assignee_type=assignee_type,
        assignee_id=assignee_id,
    )


def actions(service: ProjectService, project_id: str, user: Actor) -> list[str]:
    return [event.action for event in service.list_timeline(project_id, user=user)]


def create_agents(services: SimpleNamespace, user_id: int) -> None:
    """``threads.agent_id`` is a hard foreign key, so the assignees must exist."""
    services.agent_repo.create(agent_id=EXPERT_ID, user_id=user_id, name="Expert")
    services.agent_repo.create(agent_id=TEAM_ID, user_id=user_id, name="Team", kind="team")


# ── prompt assembly (AC-09), no runtime involved ─────────────────────────────


def test_prompt_carries_title_description_and_acceptance_section() -> None:
    prompt = build_dispatch_prompt(
        project_name="Alpha",
        task_title="看板拖拽",
        description=DESCRIPTION,
        link="/projects/prj_1?task=tsk_1",
    )
    assert prompt == EXPECTED_PROMPT.format(project_id="prj_1", task_id="tsk_1")


def test_acceptance_section_is_split_out_of_the_description() -> None:
    body, acceptance = split_acceptance(DESCRIPTION)
    assert body == "把看板拖拽做完。"
    assert acceptance == "- 拖拽后状态列立即更新\n- 刷新后状态保持"
    assert split_acceptance("没有验收标准") == ("没有验收标准", "")


def test_prompt_keeps_the_sections_when_the_task_has_no_text() -> None:
    prompt = build_dispatch_prompt(
        project_name="Alpha", task_title="T", description="", link=task_link("p1", "t1")
    )
    assert "## 任务描述\n（无描述）" in prompt
    assert "## 验收标准\n（未填写验收标准）" in prompt
    assert prompt.endswith("任务链接：/projects/p1?task=t1")


# ── rejections ───────────────────────────────────────────────────────────────


async def test_dispatch_rejects_assignee_types_that_cannot_run(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    """A human / missing assignee is a caller error — 409, never an unhandled 500."""
    service, manager, gateway = build(services)
    create_agents(services, owner.id)
    human = make_task(service, project, owner, assignee_type="user", assignee_id=str(owner.id))
    unassigned = make_task(service, project, owner, assignee_type=None, assignee_id=None)

    for task in (human, unassigned):
        with pytest.raises(OctopError) as err:
            await service.dispatch_task(project.id, task.id, user=owner)
        assert err.value.code is ErrorCode.PROJECT_TASK_DISPATCH_INVALID
        assert err.value.status == 409
        assert err.value.status != 500

    assert manager.streams == []
    assert gateway.teams.stamped == []


async def test_dispatch_rejects_an_agent_task_without_an_assignee_id(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    """The second malformed branch: a runnable type with an empty assignee id."""
    service, manager, gateway = build(services)
    create_agents(services, owner.id)
    nameless = make_task(service, project, owner, assignee_type="agent", assignee_id=None)

    with pytest.raises(OctopError) as err:
        await service.dispatch_task(project.id, nameless.id, user=owner)
    assert err.value.code is ErrorCode.PROJECT_TASK_DISPATCH_INVALID
    assert err.value.status == 409
    assert err.value.status != 500
    assert manager.streams == []
    assert gateway.teams.stamped == []


async def test_dispatch_rejects_a_missing_task(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    service, _, _ = build(services)
    with pytest.raises(OctopError) as err:
        await service.dispatch_task(project.id, "nope", user=owner)
    assert err.value.code is ErrorCode.PROJECT_TASK_NOT_FOUND


async def test_dispatch_rejects_a_task_from_another_project(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    service, manager, _ = build(services)
    create_agents(services, owner.id)
    other = service.create_project(owner_user=owner, name="Beta")
    foreign = make_task(service, other, owner)

    with pytest.raises(OctopError) as err:
        await service.dispatch_task(project.id, foreign.id, user=owner)
    assert err.value.code is ErrorCode.PROJECT_TASK_NOT_FOUND
    assert manager.streams == []


async def test_dispatch_rejects_a_non_member(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    service, manager, _ = build(services)
    create_agents(services, owner.id)
    task = make_task(service, project, owner)
    outsider = Actor(services.user_repo.create(username="out", password_hash="h", role="user"))

    with pytest.raises(OctopError) as err:
        await service.dispatch_task(project.id, task.id, user=outsider)
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
    assert manager.streams == []


async def test_dispatch_rejects_a_viewer(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    """Dispatching starts work, so it needs the same level as editing a task."""
    service, manager, _ = build(services)
    create_agents(services, owner.id)
    task = make_task(service, project, owner)
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
        await service.dispatch_task(project.id, task.id, user=viewer)
    assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN
    assert manager.streams == []


async def test_dispatch_without_a_runtime_is_not_running(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    """A service built without the server runtime cannot start any turn."""
    service = ProjectService(services)
    task = service.create_task(project.id, user=owner, title="T", assignee_type="agent")

    with pytest.raises(OctopError) as err:
        await service.dispatch_task(project.id, task.id, user=owner)
    assert err.value.code is ErrorCode.AGENT_NOT_RUNNING


# ── assignee state ───────────────────────────────────────────────────────────


async def test_dispatch_unknown_assignee_agent_is_not_found(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    service, manager, gateway = build(services)
    create_agents(services, owner.id)
    task = make_task(service, project, owner, assignee_id="ag-ghost")

    with pytest.raises(OctopError) as err:
        await service.dispatch_task(project.id, task.id, user=owner)
    assert err.value.code is ErrorCode.AGENT_NOT_FOUND
    assert manager.streams == []
    assert gateway.locked == []


async def test_dispatch_stopped_assignee_agent_is_not_running(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    service, manager, gateway = build(services, running=set())
    create_agents(services, owner.id)
    task = make_task(service, project, owner)

    with pytest.raises(OctopError) as err:
        await service.dispatch_task(project.id, task.id, user=owner)
    assert err.value.code is ErrorCode.AGENT_NOT_RUNNING
    assert manager.streams == []
    # Rejected before step ①: no stray thread, no session, nothing to clean up.
    assert services.thread_repo.list_by_agent(agent_id=EXPERT_ID) == []
    assert gateway.locked == []


# ── happy path (stubbed turn) ────────────────────────────────────────────────


async def test_dispatch_creates_a_thread_binds_the_task_and_records_the_timeline(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    service, manager, gateway = build(services)
    create_agents(services, owner.id)
    task = make_task(service, project, owner)

    dispatched = await service.dispatch_task(project.id, task.id, user=owner)

    # ① thread created for the assignee, on its own dispatch session (SPEC B30) —
    #    never the dispatcher's private DM session.
    assert dispatched.thread_id is not None
    thread = services.thread_repo.get(dispatched.thread_id)
    assert thread is not None
    assert (thread.agent_id, thread.user_id) == (EXPERT_ID, owner.id)
    assert thread.session_key == dispatch_session_key(agent_id=EXPERT_ID, dispatch_id=task.id)
    assert thread.session_key != ThreadRegistry.dashboard_key(agent_id=EXPERT_ID, user_id=owner.id)

    # ⑤ the task carries the thread.
    assert service.get_task(project.id, task.id, user=owner).thread_id == dispatched.thread_id

    # ③ one turn, for the assignee, under the session lock, with the task thread.
    assert gateway.locked == [(EXPERT_ID, thread.session_key)]
    assert [agent_id for agent_id, _ in manager.streams] == [EXPERT_ID]
    request = manager.streams[0][1]
    assert request["thread_id"] == dispatched.thread_id
    assert request["agent_id"] == EXPERT_ID
    assert request["configurable"]["session_key"] == thread.session_key

    # ④ an expert assignee never touches the team room.
    assert gateway.teams.stamped == []

    # ⑥ timeline row.
    assert actions(service, project.id, owner) == [TIMELINE_TASK_CREATED, TIMELINE_TASK_DISPATCHED]
    event = service.list_timeline(project.id, user=owner)[-1]
    assert event.task_id == task.id
    assert event.actor == actor_ref("user", owner.id)
    assert event.payload == {
        "assignee_type": "agent",
        "assignee_id": EXPERT_ID,
        "thread_id": dispatched.thread_id,
    }


async def test_dispatch_projects_the_prompt_as_the_first_thread_message(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    """AC-09 at the persistence level: what the assignee actually reads."""
    service, _, _ = build(services)
    create_agents(services, owner.id)
    task = make_task(service, project, owner)

    dispatched = await service.dispatch_task(project.id, task.id, user=owner)

    assert dispatched.thread_id is not None
    page, _has_more = services.thread_message_repo.page(dispatched.thread_id, limit=10)
    assert [row.role for row in page] == ["human", "ai"]
    first = page[0].message_json
    assert "看板拖拽" in first
    assert "把看板拖拽做完。" in first
    assert "## 验收标准" in first
    assert "刷新后状态保持" in first
    assert f"/projects/{project.id}?task={task.id}" in first
    assert REPLY in page[1].message_json


async def test_dispatch_team_assignee_runs_the_host_and_stamps_the_room(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    """④ a team task runs the team host, with its runtime stamped for the room.

    Only the stamping is asserted — ``ask_agent`` reaching the members needs a real
    provider, so that half stays unverified (see the module docstring).
    """
    service, manager, gateway = build(services)
    create_agents(services, owner.id)
    task = make_task(service, project, owner, assignee_type="team", assignee_id=TEAM_ID)

    dispatched = await service.dispatch_task(project.id, task.id, user=owner)

    assert [agent_id for agent_id, _ in manager.streams] == [TEAM_ID]
    request = manager.streams[0][1]
    assert gateway.teams.stamped == [(request, TEAM_ID)]
    assert dispatched.thread_id == request["thread_id"]
    assert service.get_task(project.id, task.id, user=owner).thread_id == dispatched.thread_id


async def test_dispatch_writes_nothing_when_the_turn_fails(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    service, manager, _ = build(services, failure=RuntimeError("turn exploded"))
    create_agents(services, owner.id)
    task = make_task(service, project, owner)

    with pytest.raises(RuntimeError, match="turn exploded"):
        await service.dispatch_task(project.id, task.id, user=owner)

    assert [agent_id for agent_id, _ in manager.streams] == [EXPERT_ID]
    assert service.get_task(project.id, task.id, user=owner).thread_id is None
    assert actions(service, project.id, owner) == [TIMELINE_TASK_CREATED]


# ── SPEC B30: a dispatch runs on its own key, never on the user's private DM ──


def test_dispatch_session_key_never_takes_the_user_dm_shape() -> None:
    """B30 ① — pure: the dispatch key is dispatch-scoped for every assignee."""
    for agent_id in ("ag-1", "CGV8GA"):
        key = dispatch_session_key(agent_id=agent_id, dispatch_id="tsk_1")
        assert key == f"{agent_id}:dashboard:tsk_1:dispatch"
        assert key != ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=1)
        # A non-DM key passes the guard untouched.
        assert require_dispatch_session_key(key) == key


async def test_dispatch_keeps_the_user_dm_session_thread_id_verbatim(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    """B30 ① — one dispatch must not rebind the dispatcher's private DM session.

    The DM session exists first (as it does in production: the user has chatted
    with the assignee); after a dispatch its bound thread has to be the very same
    id, because that binding *is* the conversation.
    """
    service, _, gateway = build(services)
    create_agents(services, owner.id)
    task = make_task(service, project, owner)

    dm_key = ThreadRegistry.dashboard_key(agent_id=EXPERT_ID, user_id=owner.id)
    dm_thread_id = await gateway.thread_registry.get_or_create(
        agent_id=EXPERT_ID,
        user_id=owner.id,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        channel_subject_id=str(owner.id),
        channel_chat_type=ThreadRegistry.CHAT_TYPE_DM,
    )
    before = services.session_repo.get(dm_key)
    assert before is not None
    assert before.thread_id == dm_thread_id

    dispatched = await service.dispatch_task(project.id, task.id, user=owner)

    after = services.session_repo.get(dm_key)
    assert after is not None
    assert after.thread_id == before.thread_id == dm_thread_id
    assert after.chat_type == ThreadRegistry.CHAT_TYPE_DM
    assert dispatched.thread_id != dm_thread_id


async def test_dispatch_reuses_its_own_session_without_touching_the_user_dm(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    """A re-dispatch keeps the dispatch session — its chat type is never rewritten."""
    service, _, gateway = build(services)
    create_agents(services, owner.id)
    task = make_task(service, project, owner)
    dm_key = ThreadRegistry.dashboard_key(agent_id=EXPERT_ID, user_id=owner.id)
    await gateway.thread_registry.get_or_create(
        agent_id=EXPERT_ID,
        user_id=owner.id,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        channel_subject_id=str(owner.id),
        channel_chat_type=ThreadRegistry.CHAT_TYPE_DM,
    )
    dm_before = services.session_repo.get(dm_key)
    assert dm_before is not None

    first = await service.dispatch_task(project.id, task.id, user=owner)
    second = await service.dispatch_task(project.id, task.id, user=owner)

    session = services.session_repo.get(
        dispatch_session_key(agent_id=EXPERT_ID, dispatch_id=task.id)
    )
    assert session is not None
    assert session.chat_type == DISPATCH_CHAT_TYPE
    assert session.thread_id == second.thread_id
    assert first.thread_id != second.thread_id
    dm_after = services.session_repo.get(dm_key)
    assert dm_after is not None
    assert dm_after.thread_id == dm_before.thread_id


async def test_dispatch_thread_runs_on_a_dispatch_session_not_a_dm_one(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    """B30 ② — the dispatch thread's session key is not a DM key, chat_type ≠ dm."""
    service, _, _ = build(services)
    create_agents(services, owner.id)
    task = make_task(service, project, owner)

    dispatched = await service.dispatch_task(project.id, task.id, user=owner)

    assert dispatched.thread_id is not None
    thread = services.thread_repo.get(dispatched.thread_id)
    assert thread is not None
    session = services.session_repo.get(thread.session_key)
    assert session is not None

    assert thread.session_key != ThreadRegistry.dashboard_key(agent_id=EXPERT_ID, user_id=owner.id)
    assert thread.session_key == dispatch_session_key(agent_id=EXPERT_ID, dispatch_id=task.id)
    assert session.chat_type == DISPATCH_CHAT_TYPE
    assert session.chat_type != ThreadRegistry.CHAT_TYPE_DM
    assert session.thread_id == dispatched.thread_id


async def test_dispatch_refuses_a_user_dm_key_as_the_dispatch_key(
    services: SimpleNamespace, project: Any, owner: Actor
) -> None:
    """B30 ④ — a caller-supplied DM key is a same-key conflict, never a rebind."""
    service, manager, gateway = build(services)
    create_agents(services, owner.id)
    task = make_task(service, project, owner)
    dm_key = ThreadRegistry.dashboard_key(agent_id=EXPERT_ID, user_id=owner.id)

    with pytest.raises(OctopError) as err:
        await run_dispatch_turn(
            repos=services.repos,
            agent_manager=manager,
            gateway=gateway,
            project=project,
            task=task,
            dispatcher_user_id=owner.id,
            session_key=dm_key,
        )

    assert err.value.code is ErrorCode.TEAM_RUN_CONFLICT
    assert err.value.status == 409
    assert err.value.details == {"reason": "session_key_already_bound"}
    # Refused before step ①: no thread, no session, no turn.
    assert services.thread_repo.list_by_agent(agent_id=EXPERT_ID) == []
    assert services.session_repo.get(dm_key) is None
    assert manager.streams == []
    assert gateway.locked == []


# ── routing: the ":dispatch" action suffix is literal, not part of {task_id} ──

DISPATCH_PATH = "/projects/{project_id}/tasks/{task_id}:dispatch"


def test_dispatch_route_keeps_the_action_suffix_out_of_the_task_id() -> None:
    route = next(r for r in projects_router.routes if getattr(r, "path", "") == DISPATCH_PATH)
    match, child = route.matches(  # type: ignore[attr-defined]
        {
            "type": "http",
            "method": "POST",
            "path": "/projects/prj_1/tasks/tsk_1:dispatch",
            "headers": [],
        }
    )
    assert match is Match.FULL
    assert child["path_params"] == {"project_id": "prj_1", "task_id": "tsk_1"}


def test_dispatch_route_does_not_swallow_the_sibling_task_routes() -> None:
    paths = {getattr(r, "path", "") for r in projects_router.routes}
    assert "/projects/{project_id}/tasks/{task_id}" in paths
    assert DISPATCH_PATH in paths
