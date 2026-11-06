"""Secure-form pauses: registration refusal, approval immunity, IM degradation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.agent_mcp.service import AgentMcpGatewayService
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.coordinator import (
    HitlChannelCoordinator,
    HitlStreamContext,
    approve_decisions_if_allowed,
    iter_secure_form_registration_guard,
)
from octop.infra.gateway.hitl.format import (
    format_hitl_card,
    is_secure_form_action_requests,
    is_sensitive_action_requests,
)
from octop.infra.gateway.hitl.store import HitlPendingStore

TOOL = "request_secure_form"

_VALID_ARGS: dict[str, Any] = {
    "fields": [
        {"id": "host", "label": "Host", "type": "text"},
        {"id": "password", "label": "Password", "type": "password"},
    ],
    "prompt": "Deploy credentials",
    "routing": {"kind": "env", "slots": {"host": "DEPLOY_HOST", "password": "DEPLOY_PASS"}},
}

_INVALID_ARGS: dict[str, Any] = {
    "fields": [{"id": "Bad-Id", "label": "L", "type": "text"}],
    "prompt": "p",
    "routing": {"kind": "env", "slots": {"Bad-Id": "SOME_SLOT"}},
}


def _form_actions(args: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"name": TOOL, "args": args}]


def _hitl_chunk(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "hitl_required",
        "request": {
            "action_requests": _form_actions(args),
            "review_configs": [{"action_name": TOOL, "allowed_decisions": ["respond"]}],
        },
    }


def _ctx() -> HitlStreamContext:
    return HitlStreamContext(
        thread_id="thr-1",
        agent_id="agent-1",
        user_id=1,
        session_key="agent-1:dashboard:1:dm",
        channel_type="dashboard",
    )


async def _aiter(chunks: list[dict[str, Any]]):
    for chunk in chunks:
        yield chunk


# ---------------------------------------------------------------- registration guard


@pytest.mark.asyncio
async def test_invalid_form_is_refused_inline_and_never_registered() -> None:
    """The pause chunk is swallowed, the turn resumes with refusal decisions."""
    resumes: list[list[dict[str, Any]]] = []

    def resume(decisions: list[dict[str, Any]]):
        resumes.append(decisions)
        return _aiter([{"type": "token", "content": "continuing"}, {"type": "done"}])

    source = _aiter(
        [
            {"type": "token", "content": "about to ask"},
            _hitl_chunk(_INVALID_ARGS),
        ]
    )
    out = [
        chunk
        async for chunk in iter_secure_form_registration_guard(
            source, agent_id="agent-1", resume=resume
        )
    ]

    # No pause surfaced: the refusal continued the turn instead.
    assert [c["type"] for c in out] == ["token", "token", "done"]
    assert not any(c["type"] == "hitl_required" for c in out)
    assert len(resumes) == 1
    decisions = resumes[0]
    assert len(decisions) == 1
    assert decisions[0]["type"] == "respond"
    assert decisions[0]["message"].startswith("The secure form request was rejected:")
    assert "Do not retry within this turn." in decisions[0]["message"]


@pytest.mark.asyncio
async def test_guard_counts_decisions_per_action_request() -> None:
    resumes: list[list[dict[str, Any]]] = []

    def resume(decisions: list[dict[str, Any]]):
        resumes.append(decisions)
        return _aiter([{"type": "done"}])

    # Two parallel request_secure_form calls pause together: the refusal must
    # carry one respond decision per action request.
    actions = [
        {"name": TOOL, "args": _INVALID_ARGS},
        {"name": TOOL, "args": _INVALID_ARGS},
    ]
    chunk = {"type": "hitl_required", "request": {"action_requests": actions}}
    out = [
        c
        async for c in iter_secure_form_registration_guard(
            _aiter([chunk]), agent_id="agent-1", resume=resume
        )
    ]
    assert out == [{"type": "done"}]
    assert len(resumes[0]) == 2


@pytest.mark.asyncio
async def test_valid_form_passes_through_untouched() -> None:
    def resume(decisions: list[dict[str, Any]]):
        raise AssertionError("valid forms must not auto-resume")

    chunk = _hitl_chunk(_VALID_ARGS)
    out = [
        c
        async for c in iter_secure_form_registration_guard(
            _aiter([{"type": "token", "content": "x"}, chunk]), agent_id="agent-1", resume=resume
        )
    ]
    assert out == [{"type": "token", "content": "x"}, chunk]


@pytest.mark.asyncio
async def test_guard_retries_are_bounded() -> None:
    """An insistent model re-pausing invalidly surfaces after max refusals."""

    def resume(decisions: list[dict[str, Any]]):
        del decisions
        return _aiter([_hitl_chunk(_INVALID_ARGS)])

    out = [
        c
        async for c in iter_secure_form_registration_guard(
            _aiter([_hitl_chunk(_INVALID_ARGS)]),
            agent_id="agent-1",
            resume=resume,
            max_refusals=2,
        )
    ]
    assert out[-1]["type"] == "hitl_required"
    assert len(out) == 1


@pytest.mark.asyncio
async def test_guard_resume_failure_propagates() -> None:
    """A failed refusal resume is a stream failure — there is nothing the
    user could decide on an invalid form, so the caller's normal error
    handling (history persist + error chunk) takes over."""

    def resume(decisions: list[dict[str, Any]]):
        del decisions
        raise RuntimeError("graph gone")

    with pytest.raises(RuntimeError):
        async for _chunk in iter_secure_form_registration_guard(
            _aiter([_hitl_chunk(_INVALID_ARGS)]), agent_id="agent-1", resume=resume
        ):
            pass


# ---------------------------------------------------------------- choke point


def test_register_from_request_refuses_invalid_form() -> None:
    hitl = HitlChannelCoordinator()
    with pytest.raises(OctopError) as err:
        hitl.register_from_request(_hitl_chunk(_INVALID_ARGS)["request"], ctx=_ctx())
    assert err.value.code == ErrorCode.SECURE_FORM_REQUEST_INVALID
    assert hitl.store.list_pending_for_session(_ctx().session_key) == []


def test_register_from_request_does_not_evict_other_pendings() -> None:
    hitl = HitlChannelCoordinator()
    existing = hitl.store.register(
        thread_id="thr-1",
        agent_id="agent-1",
        user_id=1,
        session_key="agent-1:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=[{"name": "execute", "args": {"command": "ls"}}],
        review_configs=None,
    )
    with pytest.raises(OctopError):
        hitl.register_from_request(_hitl_chunk(_INVALID_ARGS)["request"], ctx=_ctx())
    record = hitl.store.get(existing.pending_id)
    assert record is not None and record.status == "pending"


def test_register_from_request_accepts_valid_form_with_slot_reader() -> None:
    hitl = HitlChannelCoordinator(existing_secret_slots=lambda _aid: {"EXISTING_ONE"})
    record = hitl.register_from_request(_hitl_chunk(_VALID_ARGS)["request"], ctx=_ctx())
    assert is_secure_form_action_requests(record.action_requests)
    # The registered payload carries the raw schema for later re-derivation.
    assert record.action_requests[0]["args"]["routing"]["kind"] == "env"
    assert (
        hitl.store.get_pending(
            record.pending_id, session_key=_ctx().session_key, agent_id="agent-1"
        )
        is not None
    )


def test_register_from_request_enforces_capacity_via_reader() -> None:
    existing = {f"SLOT_{i}" for i in range(31)}
    hitl = HitlChannelCoordinator(existing_secret_slots=lambda _aid: existing)
    args = dict(_VALID_ARGS)
    args["routing"] = {"kind": "env", "slots": {"host": "BRAND_NEW_ONE", "password": "ALSO_NEW"}}
    with pytest.raises(OctopError) as err:
        hitl.register_from_request(_hitl_chunk(args)["request"], ctx=_ctx())
    assert "slot capacity exceeded" in str(err.value.message)


# ---------------------------------------------------------------- session bypass / approvals


def test_allow_all_session_does_not_auto_resolve_secure_form() -> None:
    policies = SimpleNamespace(allows=lambda thread_id, name: name != TOOL)
    chunk = _hitl_chunk(_VALID_ARGS)
    assert approve_decisions_if_allowed(policies, "thr-1", chunk) is None


def test_owned_tool_approval_ignores_secure_form_pauses() -> None:
    hitl = HitlChannelCoordinator()
    hitl.register_from_request(_hitl_chunk(_VALID_ARGS)["request"], ctx=_ctx())
    assert hitl.owned_tool_approval("agent-1:dashboard:1:dm", agent_id="agent-1", user_id=1) is None


def test_slash_record_resolution_refuses_secure_form_pauses() -> None:
    from octop_gateway.models import MessageEvent

    def _event_text(event: MessageEvent) -> str:
        return "\n".join(getattr(part, "text", "") for part in event.content)

    hitl = HitlChannelCoordinator()
    record = hitl.register_from_request(_hitl_chunk(_VALID_ARGS)["request"], ctx=_ctx())
    ctx = SimpleNamespace(session_key="agent-1:dashboard:1:dm", agent_id="agent-1", user_id=1)
    for approve in (True, False):
        outcome = hitl._resolve_slash_record(ctx, approve=approve, arg="", lang="en")
        assert isinstance(outcome, MessageEvent)
        assert "dashboard" in _event_text(outcome).lower()
    outcome = hitl._resolve_slash_record(ctx, approve=True, arg=record.pending_id, lang="en")
    assert isinstance(outcome, MessageEvent)
    assert "dashboard" in _event_text(outcome).lower()


# ---------------------------------------------------------------- IM degradation


def test_detection_helpers() -> None:
    assert is_secure_form_action_requests(_form_actions(_VALID_ARGS)) is True
    assert is_sensitive_action_requests(_form_actions(_VALID_ARGS)) is True
    assert is_sensitive_action_requests([{"name": "request_secret_input", "args": {}}]) is True
    assert is_sensitive_action_requests([{"name": "execute", "args": {}}]) is False
    assert is_sensitive_action_requests([]) is False


def test_format_hitl_card_renders_secure_form_notice() -> None:
    store = HitlPendingStore()
    record = store.register(
        thread_id="thr-1",
        agent_id="agent-1",
        user_id=1,
        session_key="agent-1:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=_form_actions(_VALID_ARGS),
        review_configs=None,
    )
    card = format_hitl_card(record.action_requests, pending_id=record.pending_id, locale="en")
    assert "Fields: 2" in card
    assert record.pending_id in card
    assert "dashboard" in card.lower()
    assert "approve" not in card.lower()


# ---------------------------------------------------------------- generic resume 409


@pytest.mark.asyncio
async def test_generic_resume_rejects_secure_form_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import octop.api.routers.chat.routes as chat_routes
    from octop.api.routers.chat.models import HitlResumeBody

    hitl = HitlChannelCoordinator()
    record = hitl.register_from_request(_hitl_chunk(_VALID_ARGS)["request"], ctx=_ctx())

    async def _resume_chunks(**_kwargs: Any):
        yield {"type": "done"}

    processor = SimpleNamespace(hitl_coordinator=hitl, iter_hitl_resume_chunks=_resume_chunks)
    server = SimpleNamespace(
        app_runtime=SimpleNamespace(
            gateway=SimpleNamespace(
                processor=processor,
                thread_registry=SimpleNamespace(get_thread=lambda _t: None),
            ),
            agent_registry=SimpleNamespace(),
        )
    )
    monkeypatch.setattr(chat_routes, "assert_agent_access", lambda *_a, **_k: None)
    body = HitlResumeBody(
        thread_id="thr-1",
        decisions=[{"type": "respond", "message": "forged"}],
        pending_id=record.pending_id,
    )
    user = SimpleNamespace(id=1, is_admin=False)
    request = SimpleNamespace(
        headers={"accept-language": "en"},
        url=SimpleNamespace(path="/api/agents/agent-1/chat/hitl/resume"),
        is_disconnected=None,
    )

    with pytest.raises(OctopError) as err:
        await chat_routes.resume_hitl("agent-1", body, request, user=user, server=server)  # type: ignore[arg-type]
    assert err.value.code == ErrorCode.SECURE_FORM_REQUEST_INVALID


# ---------------------------------------------------------------- agent MCP resume


@pytest.mark.asyncio
async def test_agent_mcp_resume_rejects_secure_form_pause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hitl = HitlChannelCoordinator()
    hitl.register_from_request(_hitl_chunk(_VALID_ARGS)["request"], ctx=_ctx())

    gateway = SimpleNamespace(
        processor=SimpleNamespace(hitl_coordinator=hitl),
        thread_registry=SimpleNamespace(get_thread=lambda _t: None),
    )
    service = AgentMcpGatewayService(agent_manager=SimpleNamespace(), gateway=gateway)
    monkeypatch.setattr(
        AgentMcpGatewayService,
        "_require_expert",
        lambda self, expert_id, user: SimpleNamespace(agent_id="agent-1"),
    )
    monkeypatch.setattr(
        AgentMcpGatewayService,
        "_require_mcp_thread",
        lambda self, thread_id, *, expert_id, user_id: SimpleNamespace(
            thread_id=thread_id,
            agent_id=expert_id,
            user_id=user_id,
            session_key="agent-1:dashboard:1:dm",
            channel_type="mcp",
        ),
    )
    user = SimpleNamespace(id=1, is_admin=False)

    with pytest.raises(OctopError) as err:
        await service.resume_expert(
            user,
            expert_id="agent-1",
            thread_id="thr-1",
            decisions=[{"type": "respond", "message": "client-authored"}],
        )
    assert err.value.code == ErrorCode.FORBIDDEN


# ---------------------------------------------------------------- team inline refusal


def test_team_member_refusal_constant_covers_both_tools() -> None:
    from octop.infra.agents.teams.team_manager import _MEMBER_SENSITIVE_REFUSAL

    assert "request_secret_input" in _MEMBER_SENSITIVE_REFUSAL
    assert "request_secure_form" in _MEMBER_SENSITIVE_REFUSAL
    assert "Do not call" in _MEMBER_SENSITIVE_REFUSAL
