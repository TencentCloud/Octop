"""``/team`` slash command (plan T-19).

Two things are being pinned here:

1. **It is wired to the same machinery as HTTP** — every sub-command goes through
   the injected ``TeamRunService`` and the injected ownership predicate, so there
   is no second set of run rules and no second permission model.
2. **It refuses when either seam is missing** — an unguarded ``/team <goal>``
   would create a run on a team agent the caller may not touch, which is exactly
   the action the HTTP surface answers with ``403``. That refusal is the fix for
   the escalation this command would otherwise open, so it gets its own test.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from octop_harness.slash import SlashCommand

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.slash import BufferSink, build_default_dispatcher
from octop.infra.gateway.slash.catalog import spec_for
from octop.infra.gateway.slash.ctx import SlashCtx
from octop.infra.gateway.slash.handlers import GATEWAY_HANDLERS, register_all
from octop.infra.gateway.slash.handlers.team import SUBCOMMANDS, TASK_OPS, _actor, cmd_team


def _team_row() -> Any:
    row = MagicMock()
    row.agent_id = "team-1"
    row.user_id = 7
    row.kind = "team"
    return row


def _user_row(user_id: int = 7, *, role: str = "user") -> Any:
    """A ``UserRow``-shaped subject; ``is_admin`` is deliberately absent on rows."""
    from types import SimpleNamespace

    return SimpleNamespace(
        id=user_id,
        username="u7",
        role=role,
        display_name=None,
        locale="zh",
        permissions=["projects"],
    )


def _ctx(*, team_run_service: Any = None, authorizer: Any = None, row: Any = None) -> SlashCtx:
    manager = MagicMock()
    manager.get_row.return_value = _team_row() if row is None else row
    user_repo = MagicMock()
    user_repo.get.return_value = _user_row()
    return SlashCtx(
        agent_id="team-1",
        user_id=7,
        channel_type="feishu",
        session_key="team-1:feishu:u1:dm",
        thread_registry=MagicMock(),
        agent_manager=manager,
        user_repo=user_repo,
        locale="zh",
        team_run_service=team_run_service,
        authorize_agent_action=authorizer,
    )


def _ok_authorizer(*_args: Any) -> None:
    return None


def _recording_authorizer(sink: list[tuple[Any, int]]) -> Any:
    def _record(row: Any, user_id: int) -> None:
        sink.append((row, user_id))

    return _record


async def _run(ctx: SlashCtx, args: str) -> str:
    sink = BufferSink()
    await cmd_team(build_default_dispatcher(), SlashCommand(name="team", args=args), ctx, sink)
    return "\n".join(sink.lines)


# ---------------------------------------------------------------------------
# Registration and localisation
# ---------------------------------------------------------------------------


def test_team_is_in_the_catalog_and_registered() -> None:
    spec = spec_for("team")
    assert spec is not None and spec.name == "team"
    assert "team" in GATEWAY_HANDLERS

    dispatcher = build_default_dispatcher()
    register_all(dispatcher)
    assert "team" in {name for name, _ in dispatcher.known()}


def test_team_has_zh_and_en_copy() -> None:
    spec = spec_for("team")
    assert spec is not None
    assert spec.label_en.strip() and spec.label_zh.strip()
    assert spec.description_en.strip() and spec.description_zh.strip()
    assert spec.usage.strip()


# ---------------------------------------------------------------------------
# Argument validation -> TEAM_COMMAND_UNKNOWN with the allowed list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_run_id_is_team_command_unknown_with_allowed() -> None:
    ctx = _ctx(team_run_service=MagicMock(), authorizer=_ok_authorizer)
    with pytest.raises(OctopError) as err:
        await _run(ctx, "status")
    assert err.value.code is ErrorCode.TEAM_COMMAND_UNKNOWN
    assert err.value.details["allowed"] == list(SUBCOMMANDS)


@pytest.mark.asyncio
async def test_unknown_task_op_lists_the_task_ops() -> None:
    ctx = _ctx(team_run_service=MagicMock(), authorizer=_ok_authorizer)
    with pytest.raises(OctopError) as err:
        await _run(ctx, "task RUN T9 not-an-op")
    assert err.value.code is ErrorCode.TEAM_COMMAND_UNKNOWN
    assert err.value.details["allowed"] == list(TASK_OPS)


# ---------------------------------------------------------------------------
# The escalation fix: refuse when the guard is not wired
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unwired_service_refuses_instead_of_inventing_one() -> None:
    ctx = _ctx(team_run_service=None, authorizer=_ok_authorizer)
    with pytest.raises(OctopError) as err:
        await _run(ctx, "make a plan")
    assert err.value.code is ErrorCode.TEAM_COMMAND_UNKNOWN
    assert err.value.details["reason"] == "team_run_service_unwired"


@pytest.mark.asyncio
async def test_unwired_authorizer_refuses_instead_of_weakening_the_gate() -> None:
    """Without the shared predicate, `/team <goal>` must NOT fall back to a guess.

    The service's ``create()`` does not check user-to-agent ownership itself, so
    proceeding here would let any caller in the session create a run on a team
    agent the HTTP surface would refuse with ``403``.
    """
    service = MagicMock()
    ctx = _ctx(team_run_service=service, authorizer=None)
    with pytest.raises(OctopError) as err:
        await _run(ctx, "make a plan")
    assert err.value.code is ErrorCode.TEAM_COMMAND_UNKNOWN
    assert err.value.details["reason"] == "authorizer_unwired"
    service.create.assert_not_called()


@pytest.mark.asyncio
async def test_a_refused_owner_never_reaches_the_service() -> None:
    def _deny(_row: Any, _user_id: int) -> None:
        raise OctopError(ErrorCode.FORBIDDEN, "agent not owned by user")

    service = MagicMock()
    ctx = _ctx(team_run_service=service, authorizer=_deny)
    with pytest.raises(OctopError) as err:
        await _run(ctx, "make a plan")
    assert err.value.code is ErrorCode.FORBIDDEN
    service.create.assert_not_called()


# ---------------------------------------------------------------------------
# Same machinery as HTTP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_uses_the_injected_service_and_predicate() -> None:
    seen: list[tuple[Any, int]] = []
    service = MagicMock()
    service.create.return_value = MagicMock(
        run_id="RUN1", phase="clarify", tier="standard", mode="one-shot"
    )
    ctx = _ctx(team_run_service=service, authorizer=_recording_authorizer(seen))

    text = await _run(ctx, "ship the thing")

    assert seen and seen[0][1] == 7, "the shared predicate must receive the caller id"
    assert seen[0][0].agent_id == "team-1"
    service.create.assert_called_once()
    kwargs = service.create.call_args.kwargs
    assert kwargs["team_agent_id"] == "team-1"
    assert kwargs["goal"] == "ship the thing"
    # ``create()`` needs a ProjectActor, not the bare id: id + real permissions.
    assert kwargs["user"].id == 7
    assert kwargs["user"].permissions == ["projects"]
    assert "RUN1" in text


@pytest.mark.asyncio
async def test_non_team_agent_is_team_not_found() -> None:
    plain = MagicMock()
    plain.kind = "expert"
    service = MagicMock()
    ctx = _ctx(team_run_service=service, authorizer=_ok_authorizer, row=plain)
    with pytest.raises(OctopError) as err:
        await _run(ctx, "ship the thing")
    assert err.value.code is ErrorCode.TEAM_NOT_FOUND


@pytest.mark.asyncio
async def test_status_goes_through_require_run_like_http() -> None:
    """The slash path must hit the service's own lookup, not a private query."""
    run = MagicMock(
        run_id="RUN1",
        status="running",
        phase="design",
        tier="standard",
        goal="g",
        team_agent_id="team-1",
    )
    service = MagicMock()
    service.require_run.return_value = run
    ctx = _ctx(team_run_service=service, authorizer=_ok_authorizer)

    await _run(ctx, "status RUN1")

    service.require_run.assert_called_once_with("RUN1")


# ---------------------------------------------------------------------------
# §8.1② binding: the row→User resolution must not drift from the canonical one
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolved_actor_equals_the_user_managers_user(tmp_path: Any) -> None:
    """``_actor`` must produce exactly what ``UserManager.get_by_id`` produces.

    ``UserManager``'s cache is not reachable from a ``SlashCtx``, so this handler
    converts the same ``UserRow`` itself. That is a *shape* conversion, not a
    second rule — ``is_admin`` stays ``User``'s own property — and this test is
    the machine binding that keeps the two from drifting: ``User`` is a dataclass,
    so equality covers **every** field, and a field added to ``User`` later (set by
    ``boot``, missed here) turns this red instead of silently weakening the actor.
    """
    from octop.config import OctopConfig
    from octop.infra.db.migrate import run_migrations
    from octop.infra.db.pool import SqlitePool
    from octop.infra.db.services import build_shared_services
    from octop.infra.users.manager import UserManager
    from octop.infra.utils.paths import PathLayout

    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    admin_id = services.user_repo.create(username="adm", password_hash="h", role="admin")
    plain_id = services.user_repo.create(username="usr", password_hash="h", role="user")

    manager = UserManager(services)
    await manager.boot()

    for user_id in (admin_id, plain_id):
        ctx = _ctx()
        ctx.user_id = int(user_id)
        ctx.user_repo = services.user_repo
        mine = _actor(ctx, "en")
        theirs = manager.get_by_id(int(user_id))
        assert theirs is not None
        assert mine == theirs, f"actor drifted for user {user_id}"
        # The admin flag is the canonical property, not something derived here.
        assert mine.is_admin == (theirs.role == "admin")
