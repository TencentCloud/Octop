"""Project instruction — display-only text with a zero-injection surface (PLAN.md §5).

The load-bearing claim of this feature is a *negative*: the instruction must never
reach an agent prompt (Q19). A negative assertion is only worth anything next to
proof that the text really is stored, so each such test also reads the value back
out of the database — a write that silently dropped the text would otherwise make
the test pass vacuously.

Rejection codes are asserted together with their HTTP status, and every negative
case asserts ``!= 500``: this codebase has shipped unhandled ``ValueError`` -> 500
paths before, and "the request failed" is not the same claim as "the request was
refused with the frozen code".
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.api.routers.project_instruction import (
    InstructionOut,
    InstructionUpdate,
    get_instruction,
    put_instruction,
    validate_instruction,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.project_tasks import ProjectTaskRepo, TimelineRepo
from octop.infra.db.repos.projects import (
    MEMBER_SUBJECT_USER,
    PROJECT_INSTRUCTION_MAX_LENGTH,
    ProjectMemberRepo,
    ProjectRepo,
)
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.usage import UsageRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge import service as knowledge_service_module
from octop.infra.projects import dispatch as dispatch_module
from octop.infra.projects import service as project_service_module
from octop.infra.projects.dispatch import build_dispatch_prompt, task_link
from octop.infra.projects.service import ProjectService
from octop.infra.utils.paths import PathLayout

SENTINEL_INSTRUCTION = "SENTINEL_INSTRUCTION_must_never_reach_an_agent_prompt"

INSTRUCTION = "Always answer in the project's own glossary terms."


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
    # The knowledge feature gate needs an embedding provider; the instruction is
    # not a knowledge concern, so the gate is opened (and no KB is required).
    monkeypatch.setattr(knowledge_service_module, "assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(
        project_service_module, "get_capability", lambda *_a, **_k: {"usable": False}
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
        session_repo=SessionRepo(pool),
        thread_message_repo=ThreadMessageRepo(pool),
        usage_repo=UsageRepo(pool),
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


@pytest.fixture
def server(services: SimpleNamespace) -> Any:
    """The slice of ``OctopServer`` the route helpers read.

    ``app_runtime`` is ``None`` because neither route needs an agent runtime —
    which is itself part of the point: the instruction is pure display data.
    """
    return SimpleNamespace(services=services, app_runtime=None)


def add_member(
    service: ProjectService, project_id: str, *, actor: Actor, subject_id: str, role: str
) -> None:
    service.add_member(
        project_id,
        user=actor,
        subject_type=MEMBER_SUBJECT_USER,
        subject_id=subject_id,
        role=role,
        subject_user_id=int(subject_id),
    )


async def write(server: Any, project_id: str, actor: Actor, text: str) -> InstructionOut:
    return await put_instruction(
        project_id,
        InstructionUpdate(instruction=text),
        server=server,
        user=actor,
    )


async def read(server: Any, project_id: str, actor: Actor) -> InstructionOut:
    return await get_instruction(project_id, server=server, user=actor)


def stored(services: SimpleNamespace, project_id: str) -> str:
    """The value as it lives in the database — the non-vacuity check."""
    row = services.project_repo.get(project_id)
    assert row is not None
    return row.instruction


def refusal(error: OctopError) -> tuple[ErrorCode, int]:
    return error.code, error.status


# ── round trip ───────────────────────────────────────────────────────────────


async def test_write_then_read_round_trip(
    services: SimpleNamespace, server: Any, project: Any, owner: Actor
) -> None:
    written = await write(server, project.id, owner, INSTRUCTION)

    assert written.project_id == project.id
    assert written.instruction == INSTRUCTION
    assert stored(services, project.id) == INSTRUCTION, "the text must be in the row"

    read_back = await read(server, project.id, owner)
    assert read_back.instruction == INSTRUCTION


async def test_replacing_the_instruction_overwrites_the_previous_text(
    services: SimpleNamespace, server: Any, project: Any, owner: Actor
) -> None:
    await write(server, project.id, owner, INSTRUCTION)

    replaced = await write(server, project.id, owner, "Second revision.")

    assert replaced.instruction == "Second revision."
    assert stored(services, project.id) == "Second revision."


async def test_the_instruction_is_not_the_goal_field(
    services: SimpleNamespace, server: Any, project: Any, owner: Actor
) -> None:
    """PLAN §5: same zero-injection boundary, still two different fields."""
    await write(server, project.id, owner, INSTRUCTION)

    row = services.project_repo.get(project.id)
    assert row is not None
    assert row.goal == ""
    assert row.instruction == INSTRUCTION

    services.project_repo.update(project.id, goal="Ship the release.")
    reread = services.project_repo.get(project.id)
    assert reread is not None
    assert reread.goal == "Ship the release."
    assert reread.instruction == INSTRUCTION, "editing the goal must not touch it"


# ── S12: an empty instruction is a legal write ───────────────────────────────


async def test_an_empty_string_clears_the_instruction(
    services: SimpleNamespace, server: Any, project: Any, owner: Actor
) -> None:
    """S12 — ``""`` clears the field and is **not** refused (the UI shows a placeholder)."""
    await write(server, project.id, owner, INSTRUCTION)

    cleared = await write(server, project.id, owner, "")

    assert cleared.instruction == ""
    assert stored(services, project.id) == ""
    assert (await read(server, project.id, owner)).instruction == ""


# ── length and character rules (400, never 500) ──────────────────────────────


async def test_the_frozen_cap_is_two_thousand_characters() -> None:
    assert PROJECT_INSTRUCTION_MAX_LENGTH == 2000


async def test_text_at_the_cap_is_accepted(
    services: SimpleNamespace, server: Any, project: Any, owner: Actor
) -> None:
    text = "x" * PROJECT_INSTRUCTION_MAX_LENGTH

    assert (await write(server, project.id, owner, text)).instruction == text
    assert stored(services, project.id) == text


async def test_text_over_the_cap_is_refused_with_400(
    services: SimpleNamespace, server: Any, project: Any, owner: Actor
) -> None:
    await write(server, project.id, owner, INSTRUCTION)

    with pytest.raises(OctopError) as err:
        await write(server, project.id, owner, "x" * (PROJECT_INSTRUCTION_MAX_LENGTH + 1))

    assert refusal(err.value) == (ErrorCode.PROJECT_INSTRUCTION_INVALID, 400)
    assert err.value.status != 500
    assert err.value.message
    assert stored(services, project.id) == INSTRUCTION, "a refused write changes nothing"


@pytest.mark.parametrize(
    "text",
    [
        "nul\x00byte",
        "escape\x1b[31mred",
        "carriage\rreturn",
        "vertical\x0btab",
    ],
)
async def test_control_characters_are_refused_with_400(
    server: Any, project: Any, owner: Actor, text: str
) -> None:
    with pytest.raises(OctopError) as err:
        await write(server, project.id, owner, text)

    assert refusal(err.value) == (ErrorCode.PROJECT_INSTRUCTION_INVALID, 400)
    assert err.value.status != 500


@pytest.mark.parametrize("text", ["first line\nsecond line", "col\tcol", "plain text"])
def test_newlines_and_tabs_stay_legal(text: str) -> None:
    assert validate_instruction(text) == text


@pytest.mark.parametrize("text", ["", "line\nline", "x" * 2000])
def test_the_validator_accepts_every_legal_shape(text: str) -> None:
    assert validate_instruction(text) == text


# ── permissions: read for members, config level for writes ───────────────────


async def test_every_member_may_read(
    service: ProjectService, server: Any, project: Any, owner: Actor
) -> None:
    await write(server, project.id, owner, INSTRUCTION)
    viewer = Actor(owner.id + 101)
    member = Actor(owner.id + 102)
    add_member(service, project.id, actor=owner, subject_id=str(viewer.id), role="viewer")
    add_member(service, project.id, actor=owner, subject_id=str(member.id), role="member")

    assert (await read(server, project.id, owner)).instruction == INSTRUCTION
    assert (await read(server, project.id, viewer)).instruction == INSTRUCTION
    assert (await read(server, project.id, member)).instruction == INSTRUCTION


async def test_only_owner_and_admin_may_write(
    service: ProjectService, services: SimpleNamespace, server: Any, project: Any, owner: Actor
) -> None:
    """``member`` holds ``PROJECT_WRITE`` but not ``MANAGE_CONFIG`` (R18)."""
    viewer = Actor(owner.id + 111)
    member = Actor(owner.id + 112)
    proj_admin = Actor(owner.id + 113)
    add_member(service, project.id, actor=owner, subject_id=str(viewer.id), role="viewer")
    add_member(service, project.id, actor=owner, subject_id=str(member.id), role="member")
    add_member(service, project.id, actor=owner, subject_id=str(proj_admin.id), role="admin")

    for denied in (viewer, member):
        with pytest.raises(OctopError) as err:
            await write(server, project.id, denied, SENTINEL_INSTRUCTION)
        assert refusal(err.value) == (ErrorCode.PROJECT_ROLE_FORBIDDEN, 403)
        assert err.value.status != 500

    assert stored(services, project.id) == "", "refused writers must not have written"

    assert (await write(server, project.id, proj_admin, INSTRUCTION)).instruction == INSTRUCTION
    assert (await write(server, project.id, owner, "Owner revision.")).instruction == (
        "Owner revision."
    )


async def test_a_non_member_cannot_read_or_write(
    services: SimpleNamespace, service: ProjectService, server: Any, project: Any, owner: Actor
) -> None:
    outsider = Actor(
        services.user_repo.create(username="outsider", password_hash="h", role="admin"),
        admin=True,
    )

    with pytest.raises(OctopError) as err:
        await read(server, project.id, outsider)
    assert refusal(err.value) == (ErrorCode.PROJECT_FORBIDDEN, 403)

    with pytest.raises(OctopError) as err:
        await write(server, project.id, outsider, SENTINEL_INSTRUCTION)
    assert refusal(err.value) == (ErrorCode.PROJECT_FORBIDDEN, 403)
    assert stored(services, project.id) == ""


async def test_an_archived_project_refuses_the_write(
    service: ProjectService, services: SimpleNamespace, server: Any, project: Any, owner: Actor
) -> None:
    """Archived projects are read-only for every action but ``read``."""
    service.transition_project(project.id, user=owner, target="active")
    service.transition_project(project.id, user=owner, target="archived")

    with pytest.raises(OctopError) as err:
        await write(server, project.id, owner, INSTRUCTION)

    assert refusal(err.value) == (ErrorCode.PROJECT_FORBIDDEN, 403)
    assert stored(services, project.id) == ""


# ── ★ zero-injection surface (Q19) ───────────────────────────────────────────


async def test_the_dispatch_prompt_never_carries_the_instruction(
    services: SimpleNamespace, server: Any, project: Any, owner: Actor
) -> None:
    """Q19: writing the text must not put it in front of any agent.

    The prompt is built by :func:`build_dispatch_prompt` — the one and only
    project -> agent text path — so asserting on its text (while the row really
    holds the sentinel) is the direct evidence for the "zero injection" claim.
    """
    await write(server, project.id, owner, SENTINEL_INSTRUCTION)
    row = services.project_repo.get(project.id)
    assert row is not None
    assert row.instruction == SENTINEL_INSTRUCTION, "non-vacuity: the text is stored"

    prompt = build_dispatch_prompt(
        project_name=row.name,
        task_title="Ship the release",
        description="Finish the changelog.",
        link=task_link(row.id, "tsk_0001"),
    )

    assert SENTINEL_INSTRUCTION not in prompt
    # …while the prompt is still the real briefing, i.e. we built the right thing.
    assert row.name in prompt
    assert "Ship the release" in prompt
    assert "Finish the changelog." in prompt
    assert task_link(row.id, "tsk_0001") in prompt


def test_build_dispatch_prompt_takes_no_instruction_argument() -> None:
    """The prompt builder cannot receive the text: adding the parameter is the regression."""
    assert "instruction" not in inspect.signature(build_dispatch_prompt).parameters


def test_the_dispatch_module_has_no_instruction_reference() -> None:
    """The in-test twin of ``grep -rn instruction src/octop/infra/projects/dispatch.py``."""
    source = inspect.getsource(dispatch_module)

    # Guard against a vacuous scan: the slice really is the dispatch module.
    assert "build_dispatch_prompt" in source
    assert "instruction" not in source
