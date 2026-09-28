"""Project cron jobs — own-jobs visibility, defensive redaction, writability (PLAN §3).

The two visibility tests are deliberately **independent**:

1. main behaviour — the project list contains only the caller's own jobs (asserted
   on the row/cron_id set, not on text);
2. defensive invariant — ``serialize_job`` is called **directly with a foreign row**
   (filter bypassed), and must still return ``prompt=None`` +
   ``prompt_hidden=True`` with no sentinel in the serialized response.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.api.routers.project_cron import (
    ProjectCronCreate,
    ProjectCronPatch,
    create_project_cron,
    delete_project_cron,
    list_project_cron,
    patch_project_cron,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.cron import CronJobRepo
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.project_tasks import ProjectTaskRepo, TimelineRepo
from octop.infra.db.repos.projects import ProjectMemberRepo, ProjectRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge import service as knowledge_service_module
from octop.infra.projects import service as project_service_module
from octop.infra.projects.cron import ProjectCronService
from octop.infra.projects.service import ProjectService
from octop.infra.utils.paths import PathLayout

SENTINEL = "SENTINEL_CRON_PROMPT"
AGENT_ID = "ag-exec"


class StubRegistry:
    """Registry stand-in: ``running`` decides whether the executor looks alive."""

    def __init__(self, running: bool) -> None:
        self.running = running

    def get_agent(self, agent_id: str) -> Any:
        if not self.running:
            raise OctopError(ErrorCode.AGENT_NOT_RUNNING, f"agent {agent_id!r} not running")
        return SimpleNamespace(agent_id=agent_id)


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
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
        agent_repo=AgentRepo(pool),
        thread_repo=ThreadRepo(pool),
        cron_repo=CronJobRepo(pool),
        paths=PathLayout.from_env(),
    )
    service = ProjectService(services)
    owner = Actor(services.user_repo.create(username="owner", password_hash="h", role="user"))
    admin = Actor(services.user_repo.create(username="admin", password_hash="h", role="user"))
    member = Actor(services.user_repo.create(username="member", password_hash="h", role="user"))
    project = service.create_project(owner_user=owner, name="Apollo")
    for actor, role in ((admin, "admin"), (member, "member")):
        service.add_member(
            project.id,
            user=owner,
            subject_type="user",
            subject_id=str(actor.id),
            role=role,
            subject_user_id=actor.id,
        )
    # The executor must exist as an agent row (hard FK) and as an agent member.
    services.agent_repo.create(agent_id=AGENT_ID, user_id=owner.id, name="Executor")
    service.add_member(
        project.id,
        user=owner,
        subject_type="agent",
        subject_id=AGENT_ID,
        role="member",
    )
    services.project_id = project.id
    services.owner = owner
    services.admin = admin
    services.member = member
    services.service = service
    services.cron = ProjectCronService(services, project_service=service)
    return services


class Actor:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.permissions = ["projects", "knowledge_bases"]

    @property
    def is_admin(self) -> bool:
        return False


def _server(services: SimpleNamespace, registry: StubRegistry | None = None) -> SimpleNamespace:
    """A server-shaped stub: the handlers build their own service from ``app_runtime``."""
    registry = registry or StubRegistry(running=True)
    services.cron._registry = registry
    return SimpleNamespace(services=services, app_runtime=SimpleNamespace(agent_registry=registry))


def _rows(services: SimpleNamespace) -> list[tuple[str, str]]:
    with services.db.connect() as conn:
        rows = conn.execute(
            "SELECT cron_id, project_id FROM cron_jobs ORDER BY created_at"
        ).fetchall()
    return [(str(row["cron_id"]), str(row["project_id"])) for row in rows]


# ── CRUD (AC-CFG-5, narrowed to "my own job") ────────────────────────────────


async def test_create_list_patch_toggle_delete_my_own_job(env: SimpleNamespace) -> None:
    server = _server(env)
    created = await create_project_cron(
        env.project_id,
        ProjectCronCreate(
            name="nightly", agent_id=AGENT_ID, schedule_spec="@every 1h", prompt=SENTINEL
        ),
        server=server,
        user=env.owner,
    )
    assert created.cron_id and created.owned_by_me is True
    assert created.prompt == SENTINEL
    assert created.agent_running is True
    rows = _rows(env)
    assert len(rows) == 1 and rows[0][1] == env.project_id, "the row carries project_id"

    listed = await list_project_cron(env.project_id, server=server, user=env.owner)
    assert [job.cron_id for job in listed] == [created.cron_id]

    patched = await patch_project_cron(
        env.project_id,
        created.cron_id,
        ProjectCronPatch(name="renamed", enabled=False),
        server=server,
        user=env.owner,
    )
    assert (patched.name, patched.enabled) == ("renamed", False)

    deleted = await delete_project_cron(
        env.project_id, created.cron_id, server=server, user=env.owner
    )
    assert deleted == {"deleted": True}
    assert _rows(env) == []


async def test_agent_must_be_a_member_agent(env: SimpleNamespace) -> None:
    with pytest.raises(OctopError) as err:
        await create_project_cron(
            env.project_id,
            ProjectCronCreate(agent_id="ag-ghost", schedule_spec="@every 1h", prompt="x"),
            server=_server(env),
            user=env.owner,
        )
    assert err.value.code is ErrorCode.PROJECT_CRON_INVALID
    assert err.value.status == 409
    assert _rows(env) == []


async def test_a_job_from_another_project_is_404(env: SimpleNamespace) -> None:
    server = _server(env)
    created = await create_project_cron(
        env.project_id,
        ProjectCronCreate(agent_id=AGENT_ID, schedule_spec="@every 1h", prompt="x"),
        server=server,
        user=env.owner,
    )
    other = env.service.create_project(owner_user=env.owner, name="Borealis")
    with pytest.raises(OctopError) as err:
        await patch_project_cron(
            other.id, created.cron_id, ProjectCronPatch(name="nope"), server=server, user=env.owner
        )
    assert err.value.code is ErrorCode.PROJECT_NOT_FOUND
    assert err.value.status == 404


# ── main behaviour: the list is mine only ────────────────────────────────────


async def test_main_behaviour_the_list_only_contains_my_own_jobs(env: SimpleNamespace) -> None:
    server = _server(env)
    mine = await create_project_cron(
        env.project_id,
        ProjectCronCreate(agent_id=AGENT_ID, schedule_spec="@every 1h", prompt=SENTINEL),
        server=server,
        user=env.owner,
    )
    # A second job, also on this project, created by the admin (a different user).
    theirs = await create_project_cron(
        env.project_id,
        ProjectCronCreate(agent_id=AGENT_ID, schedule_spec="@every 1h", prompt="admin prompt"),
        server=server,
        user=env.admin,
    )
    assert len(_rows(env)) == 2, "both rows exist in the database"

    as_member = await list_project_cron(env.project_id, server=server, user=env.member)
    assert [job.cron_id for job in as_member] == [], "a member sees neither job"

    as_admin = await list_project_cron(env.project_id, server=server, user=env.admin)
    assert {job.cron_id for job in as_admin} == {theirs.cron_id}
    assert SENTINEL not in json.dumps([job.model_dump() for job in as_admin])

    as_owner = await list_project_cron(env.project_id, server=server, user=env.owner)
    assert {job.cron_id for job in as_owner} == {mine.cron_id}


# ── defensive invariant: independent of the filter ───────────────────────────


def test_defensive_invariant_redacts_a_foreign_row(env: SimpleNamespace) -> None:
    """Bypass the filter entirely: a foreign row still must not leak its prompt."""
    env.cron._registry = StubRegistry(running=True)
    foreign = env.cron._jobs.get(
        env.cron._jobs.create(
            cron_id="cron_foreign",
            agent_id=AGENT_ID,
            user_id=env.owner.id,  # owned by the OWNER…
            trigger="@every 1h",
            prompt=SENTINEL,
            session_key="ag-exec:cron:1:dm",
            project_id=env.project_id,
        )
    )
    assert foreign is not None

    payload = env.cron.serialize_job(foreign, user_id=env.member.id)  # …read as the MEMBER

    assert payload["owned_by_me"] is False
    assert payload["prompt"] is None, "the plaintext prompt must never be echoed"
    assert payload["prompt_hidden"] is True
    assert SENTINEL not in json.dumps(payload)

    # And the same row read by its owner is intact (the redaction is per-viewer).
    own_view = env.cron.serialize_job(foreign, user_id=env.owner.id)
    assert own_view["prompt"] == SENTINEL and own_view["prompt_hidden"] is False


# ── writability is mine only (FIND-4) ────────────────────────────────────────


async def test_even_the_admin_cannot_edit_someone_elses_job(env: SimpleNamespace) -> None:
    server = _server(env)
    created = await create_project_cron(
        env.project_id,
        ProjectCronCreate(agent_id=AGENT_ID, schedule_spec="@every 1h", prompt=SENTINEL),
        server=server,
        user=env.owner,
    )
    for actor in (env.admin, env.member):
        with pytest.raises(OctopError) as err:
            await patch_project_cron(
                env.project_id,
                created.cron_id,
                ProjectCronPatch(enabled=False),
                server=server,
                user=actor,
            )
        assert err.value.status == 403
        assert err.value.code in {
            ErrorCode.PROJECT_FORBIDDEN,
            ErrorCode.PROJECT_ROLE_FORBIDDEN,
        }
    with pytest.raises(OctopError):
        await delete_project_cron(env.project_id, created.cron_id, server=server, user=env.admin)
    assert len(_rows(env)) == 1, "the refused writes changed nothing"


# ── S4: a stopped executor does not hide the job ─────────────────────────────


async def test_s4_a_stopped_agent_is_listed_with_a_flag(env: SimpleNamespace) -> None:
    created = await create_project_cron(
        env.project_id,
        ProjectCronCreate(agent_id=AGENT_ID, schedule_spec="@every 1h", prompt="x"),
        server=_server(env),
        user=env.owner,
    )
    listed = await list_project_cron(
        env.project_id, server=_server(env, StubRegistry(running=False)), user=env.owner
    )
    assert [job.cron_id for job in listed] == [created.cron_id], "still listed"
    assert listed[0].agent_running is False
    assert listed[0].enabled is True, "S4 must not disable the job"
