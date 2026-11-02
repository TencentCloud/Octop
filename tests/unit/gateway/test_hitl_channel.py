"""Unit tests for IM channel HITL."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
from octop_gateway.models import MessageEvent, MessageEventType, TextContent

from octop.infra.gateway.hitl.coordinator import (
    HitlChannelCoordinator,
    HitlSlashOutcome,
    HitlStreamContext,
)
from octop.infra.gateway.hitl.format import format_hitl_card, parse_action_requests
from octop.infra.gateway.hitl.store import HitlPendingStore
from octop.infra.gateway.process.stream_project import (
    StreamProjectionState,
    project_resume_stream,
    project_stream,
)


def test_parse_action_requests() -> None:
    raw = {
        "action_requests": [
            {"name": "execute", "args": {"command": "ls"}, "description": "run ls"},
        ]
    }
    actions = parse_action_requests(raw)
    assert len(actions) == 1
    assert actions[0]["name"] == "execute"
    assert actions[0]["args"] == {"command": "ls"}


def test_parse_action_requests_unwraps_interrupt_envelope() -> None:
    from octop.infra.gateway.hitl.format import normalize_hitl_request

    raw = {
        "id": "int-1",
        "value": {
            "action_requests": [
                {
                    "name": "ask_user_question",
                    "args": {"questions": [{"question": "Which DB?"}]},
                }
            ],
            "review_configs": [
                {"action_name": "ask_user_question", "allowed_decisions": ["respond"]}
            ],
        },
    }
    assert normalize_hitl_request(raw)["action_requests"][0]["name"] == "ask_user_question"
    actions = parse_action_requests(raw)
    assert actions[0]["name"] == "ask_user_question"
    assert actions[0]["args"]["questions"][0]["question"] == "Which DB?"


def test_hitl_store_register_and_resolve() -> None:
    store = HitlPendingStore()
    record = store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=7,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    assert record.pending_id
    resolved = store.resolve_for_session("sk1")
    assert resolved is not None
    assert resolved.pending_id == record.pending_id
    store.mark_resolved(record.pending_id, "approved")
    assert store.resolve_for_session("sk1") is None


def test_format_hitl_card_contains_commands() -> None:
    text = format_hitl_card(
        [{"name": "execute", "args": {"command": "echo hi"}}],
        pending_id="ab12",
        locale="en",
    )
    assert "/approve" in text
    assert "/reject" in text
    assert "allow all" in text
    assert "ab12" in text
    zh = format_hitl_card(
        [{"name": "execute", "args": {"command": "echo hi"}}],
        pending_id="ab12",
        locale="zh",
    )
    assert "批准" in zh
    assert "本对话都允许" in zh


@pytest.mark.asyncio
async def test_project_stream_emits_hitl_card() -> None:
    async def _stream(*_args: object, **_kwargs: object):
        yield {
            "type": "hitl_required",
            "request": {
                "action_requests": [{"name": "write_file", "args": {"path": "/tmp/x"}}],
            },
        }

    agent_manager = MagicMock()
    agent_manager.stream = _stream

    coordinator = HitlChannelCoordinator()
    state = StreamProjectionState()
    events: list[MessageEvent] = []
    async for ev in project_stream(
        agent_manager,
        "agent1",
        {"thread_id": "thr1", "messages": []},
        projection_state=state,
        hitl_coordinator=coordinator,
        hitl_ctx=HitlStreamContext(
            thread_id="thr1",
            agent_id="agent1",
            user_id=1,
            session_key="sk1",
            channel_type="feishu",
        ),
    ):
        events.append(ev)

    assert state.hitl_paused is True
    assert state.hitl_pending_id
    assert len(events) == 1
    assert events[0].type == MessageEventType.MESSAGE
    text = events[0].content[0]
    assert isinstance(text, TextContent)
    assert "/approve" in text.text


@pytest.mark.asyncio
async def test_coordinator_slash_approve_resumes() -> None:
    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )

    async def _resume(*_args: object, **_kwargs: object):
        yield {"type": "token", "content": "done", "node": "agent"}

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _resume

    ctx = MagicMock()
    ctx.session_key = "sk1"
    ctx.agent_id = "agent1"
    ctx.user_id = 1
    ctx.channel_type = "feishu"
    ctx.thread_registry = MagicMock()

    from octop_harness.slash import SlashCommand

    cmd = SlashCommand(name="approve", args="")
    events: list[MessageEvent] = []
    async for ev in coordinator.iter_slash_resolution(
        cmd,
        ctx,
        agent_manager=agent_manager,
        locale="en",
    ):
        events.append(ev)

    assert any(
        isinstance(c, TextContent) and "done" in c.text
        for e in events
        if e.content
        for c in e.content
    )
    assert store.resolve_for_session("sk1") is None


@pytest.mark.asyncio
async def test_coordinator_slash_approve_wakes_team_member_without_host_resume() -> None:
    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    record = store.register(
        thread_id="thr-room",
        agent_id="host",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    record.resume_agent_id = "member"
    record.resume_thread_id = "thr-room~member"
    delivered: list[tuple[str, list[dict[str, str]]]] = []

    def deliver(pending_id: str, decisions: list[dict[str, str]]) -> bool:
        delivered.append((pending_id, decisions))
        return True

    agent_manager = MagicMock()
    ctx = MagicMock()
    ctx.session_key = "sk1"
    ctx.agent_id = "host"
    ctx.user_id = 1
    ctx.channel_type = "feishu"
    ctx.thread_registry = MagicMock()

    from octop_harness.slash import SlashCommand

    events: list[MessageEvent] = []
    async for ev in coordinator.iter_slash_resolution(
        SlashCommand(name="approve", args=""),
        ctx,
        agent_manager=agent_manager,
        locale="en",
        member_hitl=deliver,
    ):
        events.append(ev)

    assert delivered == [(record.pending_id, [{"type": "approve"}])]
    assert agent_manager.resume_hitl.call_count == 0
    assert store.get(record.pending_id) is not None
    assert store.get(record.pending_id).status == "approved"  # type: ignore[union-attr]
    assert any(
        isinstance(c, TextContent) and "Approved" in c.text
        for e in events
        if e.content
        for c in e.content
    )


@pytest.mark.asyncio
async def test_coordinator_slash_approve_invalid_pending_id() -> None:
    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )

    from octop_harness.slash import SlashCommand

    ctx = MagicMock()
    ctx.session_key = "sk1"
    ctx.agent_id = "agent1"
    ctx.user_id = 1

    cmd = SlashCommand(name="approve", args="deadbeef")
    events: list[MessageEvent] = []
    async for ev in coordinator.iter_slash_resolution(
        cmd,
        ctx,
        agent_manager=MagicMock(),
        locale="en",
    ):
        events.append(ev)

    text = "".join(
        c.text for e in events if e.content for c in e.content if isinstance(c, TextContent)
    )
    assert "deadbeef" in text
    assert store.resolve_for_session("sk1") is not None


@pytest.mark.asyncio
async def test_coordinator_resume_failure_keeps_pending() -> None:
    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    record = store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )

    agent_manager = MagicMock()

    async def _fail(*_args: object, **_kwargs: object):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    agent_manager.resume_hitl = _fail

    ctx = MagicMock()
    ctx.session_key = "sk1"
    ctx.agent_id = "agent1"
    ctx.user_id = 1
    ctx.channel_type = "feishu"
    ctx.thread_registry = MagicMock()

    from octop_harness.slash import SlashCommand

    cmd = SlashCommand(name="approve", args="")
    async for _ in coordinator.iter_slash_resolution(
        cmd,
        ctx,
        agent_manager=agent_manager,
        locale="en",
    ):
        pass

    pending = store.resolve_for_session("sk1")
    assert pending is not None
    assert pending.pending_id == record.pending_id


@pytest.mark.asyncio
async def test_project_resume_stream_nested_hitl() -> None:
    async def _resume(*_args: object, **_kwargs: object):
        yield {
            "type": "hitl_required",
            "request": {
                "action_requests": [{"name": "delete_file", "args": {"path": "/tmp/y"}}],
            },
        }

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _resume

    coordinator = HitlChannelCoordinator()
    state = StreamProjectionState()
    events: list[MessageEvent] = []
    async for ev in project_resume_stream(
        agent_manager,
        "agent1",
        "thr1",
        [{"type": "approve"}],
        projection_state=state,
        hitl_coordinator=coordinator,
        hitl_ctx=HitlStreamContext(
            thread_id="thr1",
            agent_id="agent1",
            user_id=1,
            session_key="sk1",
            channel_type="feishu",
        ),
    ):
        events.append(ev)

    assert state.hitl_paused is True
    assert state.hitl_pending_id
    assert len(events) == 1


def test_hitl_store_gc_removes_stale_resolved() -> None:
    store = HitlPendingStore(ttl_seconds=0.01)
    record = store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    store.mark_resolved(record.pending_id, "approved")
    import time

    time.sleep(0.02)
    store._gc()
    assert store.get(record.pending_id) is None


def test_hitl_store_resolve_pending_for_thread() -> None:
    store = HitlPendingStore()
    store.register(
        thread_id="thr-a",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="dashboard",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    store.register(
        thread_id="thr-b",
        agent_id="agent1",
        user_id=1,
        session_key="sk2",
        channel_type="dashboard",
        action_requests=[{"name": "write_file", "args": {"path": "x"}}],
        review_configs=None,
    )
    pending = store.resolve_pending_for_thread("thr-a", agent_id="agent1", user_id=1)
    assert pending is not None
    assert pending.action_requests[0]["name"] == "execute"
    assert store.resolve_pending_for_thread("thr-a", agent_id="agent1", user_id=2) is None
    assert store.pending_thread_ids(agent_id="agent1", user_id=1) == frozenset({"thr-a", "thr-b"})
    assert store.pending_thread_ids(agent_id="agent1", user_id=2) == frozenset()


def test_hitl_store_reuses_equivalent_pending() -> None:
    store = HitlPendingStore()
    actions = [{"name": "execute", "args": {"command": "df"}}]
    first = store.register(
        thread_id="thr-a",
        agent_id="agent1",
        user_id=1,
        session_key="sk",
        channel_type="dashboard",
        action_requests=actions,
        review_configs=None,
    )
    again = store.register(
        thread_id="thr-a",
        agent_id="agent1",
        user_id=1,
        session_key="sk",
        channel_type="dashboard",
        action_requests=[{"args": {"command": "df"}, "name": "execute"}],
        review_configs=None,
    )
    assert again is first
    assert store.get(first.pending_id) is not None
    assert store.get(first.pending_id).status == "pending"  # type: ignore[union-attr]
    replaced = store.register(
        thread_id="thr-a",
        agent_id="agent1",
        user_id=1,
        session_key="sk",
        channel_type="dashboard",
        action_requests=[{"name": "write_file", "args": {}}],
        review_configs=None,
    )
    assert replaced is not first
    assert store.get(first.pending_id).status == "expired"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_session_auto_approve_resumes_without_yielding_the_card() -> None:
    from octop.infra.agents.security.hitl_session import (
        HitlSessionPolicy,
        HitlSessionPolicyStore,
    )
    from octop.infra.gateway.hitl.coordinator import iter_with_session_auto_approve

    policies = HitlSessionPolicyStore()
    policies.set("thr-a", HitlSessionPolicy(mode="allow_all"))
    resumed: list[list[dict[str, object]]] = []

    async def first_turn():
        yield {
            "type": "hitl_required",
            "request": {"action_requests": [{"name": "execute", "args": {}}]},
        }
        yield {"type": "state_update", "data": {}}

    async def resume(decisions: list[dict[str, object]]):
        resumed.append(decisions)
        yield {"type": "token", "content": "done-after-approve"}

    chunks = [
        chunk
        async for chunk in iter_with_session_auto_approve(
            first_turn(),
            thread_id="thr-a",
            policies=policies,
            resume=resume,
        )
    ]
    assert [chunk.get("type") for chunk in chunks] == ["state_update", "token"]
    assert resumed == [[{"type": "approve"}]]


@pytest.mark.asyncio
async def test_session_auto_approve_yields_card_when_approve_is_forbidden() -> None:
    from octop.infra.agents.security.hitl_session import (
        HitlSessionPolicy,
        HitlSessionPolicyStore,
    )
    from octop.infra.gateway.hitl.coordinator import iter_with_session_auto_approve

    policies = HitlSessionPolicyStore()
    policies.set("thr-a", HitlSessionPolicy(mode="allow_all"))
    resumed: list[list[dict[str, object]]] = []

    async def first_turn():
        yield {
            "type": "hitl_required",
            "request": {
                "action_requests": [{"name": "execute", "args": {}}],
                "review_configs": [
                    {"action_name": "execute", "allowed_decisions": ["reject"]},
                ],
            },
        }

    async def resume(decisions: list[dict[str, object]]):
        resumed.append(decisions)
        yield {"type": "token", "content": "should-not-run"}

    chunks = [
        chunk
        async for chunk in iter_with_session_auto_approve(
            first_turn(),
            thread_id="thr-a",
            policies=policies,
            resume=resume,
        )
    ]
    assert [chunk.get("type") for chunk in chunks] == ["hitl_required"]
    assert resumed == []


@pytest.mark.asyncio
async def test_session_auto_approve_yields_card_when_resume_fails() -> None:
    from octop.infra.agents.security.hitl_session import (
        HitlSessionPolicy,
        HitlSessionPolicyStore,
    )
    from octop.infra.gateway.hitl.coordinator import iter_with_session_auto_approve

    policies = HitlSessionPolicyStore()
    policies.set("thr-a", HitlSessionPolicy(mode="allow_all"))

    async def first_turn():
        yield {
            "type": "hitl_required",
            "request": {"action_requests": [{"name": "execute", "args": {}}]},
        }

    async def resume(_decisions: list[dict[str, object]]):
        raise RuntimeError("graph rejected approve")
        yield {"type": "token", "content": "unused"}  # pragma: no cover

    chunks = [
        chunk
        async for chunk in iter_with_session_auto_approve(
            first_turn(),
            thread_id="thr-a",
            policies=policies,
            resume=resume,
        )
    ]
    assert [chunk.get("type") for chunk in chunks] == ["hitl_required"]


def test_hitl_store_keeps_each_team_member_pause() -> None:
    store = HitlPendingStore()
    first = store.register(
        thread_id="thr-room",
        agent_id="host",
        user_id=1,
        session_key="host:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
        resume_agent_id="doctor",
    )
    second = store.register(
        thread_id="thr-room",
        agent_id="host",
        user_id=1,
        session_key="host:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=[{"name": "write_file", "args": {}}],
        review_configs=None,
        resume_agent_id="nurse",
    )
    assert store.get(first.pending_id) is not None
    assert store.get(first.pending_id).status == "pending"  # type: ignore[union-attr]
    assert store.get(second.pending_id) is not None
    assert store.get(second.pending_id).status == "pending"  # type: ignore[union-attr]
    picked = store.resolve_pending_for_thread(
        "thr-room",
        agent_id="host",
        user_id=1,
        pending_id=first.pending_id,
    )
    assert picked is first
    again = store.register(
        thread_id="thr-room",
        agent_id="host",
        user_id=1,
        session_key="host:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=[{"name": "execute", "args": {"command": "df"}}],
        review_configs=None,
        resume_agent_id="doctor",
    )
    assert store.get(first.pending_id).status == "expired"  # type: ignore[union-attr]
    assert store.get(second.pending_id).status == "pending"  # type: ignore[union-attr]
    assert store.get(again.pending_id).status == "pending"  # type: ignore[union-attr]


def test_hitl_store_resolves_team_member_pause_from_either_thread() -> None:
    store = HitlPendingStore()
    record = store.register(
        thread_id="thr-room",
        agent_id="host",
        user_id=1,
        session_key="host:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    record.resume_agent_id = "member"
    record.resume_thread_id = "thr-room~member"
    assert store.resolve_pending_for_thread("thr-room", agent_id="host", user_id=1) is record
    assert (
        store.resolve_pending_for_thread("thr-room~member", agent_id="member", user_id=1) is record
    )
    assert store.pending_thread_ids(agent_id="host", user_id=1) == frozenset({"thr-room"})
    assert store.pending_thread_ids(agent_id="member", user_id=1) == frozenset({"thr-room~member"})


def test_pending_hitl_payload() -> None:
    from octop.infra.gateway.hitl.coordinator import pending_hitl_payload

    store = HitlPendingStore()
    record = store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=7,
        session_key="sk1",
        channel_type="dashboard",
        action_requests=[{"name": "execute", "args": {"command": "ls"}}],
        review_configs=None,
    )
    payload = pending_hitl_payload(
        store,
        thread_id="thr1",
        agent_id="agent1",
        user_id=7,
    )
    assert payload is not None
    assert payload["pending_id"] == record.pending_id
    assert payload["action_requests"][0]["name"] == "execute"


def test_hitl_store_get_pending_agent_mismatch() -> None:
    store = HitlPendingStore()
    record = store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    assert store.get_pending(record.pending_id, session_key="sk1", agent_id="other") is None


def test_expire_pending_for_thread_drops_history_reinject() -> None:
    store = HitlPendingStore()
    record = store.register(
        thread_id="thr-ask",
        agent_id="agent1",
        user_id=7,
        session_key="sk-ask",
        channel_type="dashboard",
        action_requests=[{"name": "ask_user_question", "args": {"questions": []}}],
        review_configs=None,
    )
    store.expire_pending_for_thread("thr-ask", agent_id="agent1", user_id=7)
    assert store.resolve_pending_for_thread("thr-ask", agent_id="agent1", user_id=7) is None
    expired = store.get(record.pending_id)
    assert expired is not None
    assert expired.status == "expired"


@pytest.mark.asyncio
async def test_slash_outcome_completed_turn() -> None:
    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )

    async def _resume(*_args: object, **_kwargs: object):
        yield {"type": "token", "content": "ok", "node": "agent"}

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _resume

    ctx = MagicMock()
    ctx.session_key = "sk1"
    ctx.agent_id = "agent1"
    ctx.user_id = 1
    ctx.channel_type = "feishu"
    ctx.thread_registry = MagicMock()

    from octop_harness.slash import SlashCommand

    outcome = HitlSlashOutcome()
    cmd = SlashCommand(name="approve", args="")
    async for _ in coordinator.iter_slash_resolution(
        cmd,
        ctx,
        agent_manager=agent_manager,
        locale="en",
        outcome=outcome,
    ):
        pass
    assert outcome.completed_turn is True


def _event_text(events: list[MessageEvent]) -> str:
    return "".join(
        c.text for e in events if e.content for c in e.content if isinstance(c, TextContent)
    )


def _approval_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.session_key = "sk1"
    ctx.agent_id = "agent1"
    ctx.user_id = 1
    ctx.channel_type = "feishu"
    ctx.thread_registry = MagicMock()
    return ctx


@pytest.mark.asyncio
async def test_utterance_approves_latest_pending_only() -> None:
    from octop.infra.gateway.hitl.phrases import ApprovalUtterance

    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    older = store.register(
        thread_id="thr-old",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "write_file", "args": {}}],
        review_configs=None,
        resume_agent_id="member",
    )
    older.created_at = time.time()
    latest = store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    latest.created_at = time.time() + 1

    async def _resume(*_args: object, **_kwargs: object):
        yield {"type": "token", "content": "done", "node": "agent"}

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _resume
    events: list[MessageEvent] = []
    async for ev in coordinator.iter_utterance_resolution(
        ApprovalUtterance(kind="once"),
        _approval_ctx(),
        agent_manager=agent_manager,
        locale="zh",
    ):
        events.append(ev)

    assert "已批准" in _event_text(events)
    assert "done" in _event_text(events)
    assert store.get(latest.pending_id) is not None
    assert store.get(latest.pending_id).status == "approved"  # type: ignore[union-attr]
    assert store.get(older.pending_id) is not None
    assert store.get(older.pending_id).status == "pending"  # type: ignore[union-attr]
    assert coordinator.session_policies.get("thr1").mode == "ask"


@pytest.mark.asyncio
async def test_utterance_allow_tool_and_allow_all_stick() -> None:
    from octop.infra.gateway.hitl.phrases import ApprovalUtterance

    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}, {"name": "write_file", "args": {}}],
        review_configs=None,
    )

    async def _resume(*_args: object, **_kwargs: object):
        yield {"type": "token", "content": "done", "node": "agent"}

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _resume
    async for _ in coordinator.iter_utterance_resolution(
        ApprovalUtterance(kind="tool"),
        _approval_ctx(),
        agent_manager=agent_manager,
        locale="en",
    ):
        pass
    policy = coordinator.session_policies.get("thr1")
    assert policy.mode == "allow_tools"
    assert policy.tools == ("execute", "write_file")

    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    events: list[MessageEvent] = []
    async for ev in coordinator.iter_utterance_resolution(
        ApprovalUtterance(kind="all"),
        _approval_ctx(),
        agent_manager=agent_manager,
        locale="en",
    ):
        events.append(ev)
    assert coordinator.session_policies.get("thr1").mode == "allow_all"
    assert "Later tool approvals" in _event_text(events)


@pytest.mark.asyncio
async def test_utterance_allow_all_skips_followup_tool_but_not_question() -> None:
    from octop.infra.gateway.hitl.phrases import ApprovalUtterance

    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    calls = {"n": 0}

    async def _resume(*_args: object, **_kwargs: object):
        calls["n"] += 1
        if calls["n"] == 1:
            yield {
                "type": "hitl_required",
                "request": {"action_requests": [{"name": "execute", "args": {"command": "ls"}}]},
            }
            return
        yield {"type": "token", "content": "done", "node": "agent"}

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _resume
    events: list[MessageEvent] = []
    async for ev in coordinator.iter_utterance_resolution(
        ApprovalUtterance(kind="all"),
        _approval_ctx(),
        agent_manager=agent_manager,
        locale="en",
    ):
        events.append(ev)
    text = _event_text(events)
    assert "done" in text
    assert "Tool approval required" not in text
    assert calls["n"] == 2

    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )

    async def _ask(*_args: object, **_kwargs: object):
        yield {
            "type": "hitl_required",
            "request": {
                "action_requests": [
                    {
                        "name": "ask_user_question",
                        "args": {"questions": [{"question": "Which DB?"}]},
                    }
                ]
            },
        }

    agent_manager.resume_hitl = _ask
    events = []
    async for ev in coordinator.iter_utterance_resolution(
        ApprovalUtterance(kind="once"),
        _approval_ctx(),
        agent_manager=agent_manager,
        locale="en",
    ):
        events.append(ev)
    assert "Which DB?" in _event_text(events)


def test_owned_tool_approval_ignores_other_user_and_questions() -> None:
    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=7,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    assert coordinator.owned_tool_approval("sk1", agent_id="agent1", user_id=1) is None
    assert coordinator.owned_tool_approval("sk1", agent_id="agent1", user_id=7) is not None

    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=7,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[
            {"name": "ask_user_question", "args": {"questions": [{"question": "Which?"}]}}
        ],
        review_configs=None,
    )
    assert coordinator.owned_tool_approval("sk1", agent_id="agent1", user_id=7) is None


@pytest.mark.asyncio
async def test_im_phrase_approves_without_slash() -> None:
    from types import SimpleNamespace

    from octop_gateway.models import ChannelSubject, InboundMessage

    from octop.infra.gateway.process.processor import GlobalProcessor
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher

    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    resumed: list[list[dict[str, str]]] = []

    async def _resume(_agent_id: str, _thread_id: str, decisions: list[dict[str, str]]):
        resumed.append(decisions)
        yield {"type": "token", "content": "done", "node": "agent"}

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _resume
    agent_manager.octop_config = SimpleNamespace(default_timezone="Asia/Shanghai")
    thread_registry = MagicMock()
    thread_registry.get_bound_thread_id = MagicMock(return_value="thr1")
    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(get=MagicMock(return_value=SimpleNamespace(user_id=1))),
        user_repo=MagicMock(get=MagicMock(return_value=SimpleNamespace(locale="zh"))),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        hitl=coordinator,
    )
    msg = InboundMessage(
        channel_id="c1",
        channel_type="feishu",
        tenant_id="agent1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="本对话都允许")],
        metadata={"session_key": "sk1"},
    )
    events: list[MessageEvent] = []
    async for ev in processor(msg):
        events.append(ev)
    assert resumed == [[{"type": "approve"}]]
    assert agent_manager.stream.called is False
    assert coordinator.session_policies.get("thr1").mode == "allow_all"
    assert "自动通过" in _event_text(events)
    assert store.resolve_for_session("sk1") is None


@pytest.mark.asyncio
async def test_im_phrase_does_not_steal_question_answer() -> None:
    from types import SimpleNamespace

    from octop_gateway.models import ChannelSubject, InboundMessage

    from octop.infra.gateway.process.processor import GlobalProcessor
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher

    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[
            {
                "name": "ask_user_question",
                "args": {"questions": [{"question": "用哪个库?"}]},
            }
        ],
        review_configs=None,
    )
    resumed: list[list[dict[str, str]]] = []

    async def _resume(_agent_id: str, _thread_id: str, decisions: list[dict[str, str]]):
        resumed.append(decisions)
        yield {"type": "token", "content": "ok", "node": "agent"}

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _resume
    agent_manager.octop_config = SimpleNamespace(default_timezone="Asia/Shanghai")
    thread_registry = MagicMock()
    thread_registry.get_bound_thread_id = MagicMock(return_value="thr1")
    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(get=MagicMock(return_value=SimpleNamespace(user_id=1))),
        user_repo=MagicMock(get=MagicMock(return_value=SimpleNamespace(locale="zh"))),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        hitl=coordinator,
    )
    msg = InboundMessage(
        channel_id="c1",
        channel_type="feishu",
        tenant_id="agent1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="同意")],
        metadata={"session_key": "sk1"},
    )
    async for _ in processor(msg):
        pass
    assert resumed
    assert resumed[0][0]["type"] == "respond"
    assert "同意" in resumed[0][0]["message"]
    assert coordinator.session_policies.get("thr1").mode == "ask"


def _phrase_processor(
    coordinator: HitlChannelCoordinator,
    agent_manager: MagicMock,
) -> tuple[object, MagicMock]:
    from types import SimpleNamespace

    from octop.infra.gateway.process.processor import GlobalProcessor
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher

    thread_registry = MagicMock()
    thread_registry.get_bound_thread_id = MagicMock(return_value="thr1")
    thread_registry.get_thread = MagicMock(return_value=None)
    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(get=MagicMock(return_value=SimpleNamespace(user_id=1, kind=None))),
        user_repo=MagicMock(get=MagicMock(return_value=SimpleNamespace(locale="zh"))),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        hitl=coordinator,
    )
    agent_manager.octop_config = SimpleNamespace(default_timezone="Asia/Shanghai")
    return processor, thread_registry


def _phrase_message(text: str) -> object:
    from octop_gateway.models import ChannelSubject, InboundMessage

    return InboundMessage(
        channel_id="c1",
        channel_type="feishu",
        tenant_id="agent1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text=text)],
        metadata={"session_key": "sk1"},
    )


@pytest.mark.asyncio
async def test_sticky_policy_rolls_back_when_resume_fails() -> None:
    from octop.infra.gateway.hitl.phrases import ApprovalUtterance

    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    coordinator.session_policies.set("thr1", {"mode": "allow_tools", "tools": ["write_file"]})
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )

    async def _fail(*_args: object, **_kwargs: object):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _fail
    async for _ in coordinator.iter_utterance_resolution(
        ApprovalUtterance(kind="all"),
        _approval_ctx(),
        agent_manager=agent_manager,
        locale="zh",
    ):
        pass
    restored = coordinator.session_policies.get("thr1")
    assert restored.mode == "allow_tools"
    assert restored.tools == ("write_file",)
    assert store.resolve_for_session("sk1") is not None


@pytest.mark.asyncio
async def test_sticky_restore_keeps_a_reset_made_during_resume() -> None:
    from octop.infra.gateway.hitl.phrases import ApprovalUtterance

    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    coordinator.session_policies.set("thr1", {"mode": "allow_all"})
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )

    async def _fail(*_args: object, **_kwargs: object):
        coordinator.clear_bypass(["thr1"])
        raise RuntimeError("boom")
        yield  # pragma: no cover

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _fail
    async for _ in coordinator.iter_utterance_resolution(
        ApprovalUtterance(kind="all"),
        _approval_ctx(),
        agent_manager=agent_manager,
        locale="zh",
    ):
        pass
    assert coordinator.session_policies.get("thr1").mode == "ask"


@pytest.mark.asyncio
async def test_im_approval_resume_records_turn_duration() -> None:
    import json
    from types import SimpleNamespace

    from octop.infra.gateway.process.processor import GlobalProcessor
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher

    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )

    async def _resume(_agent_id: str, _thread_id: str, _decisions: list[dict[str, str]]):
        yield {"type": "token", "content": "done", "node": "agent"}

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _resume
    appended: list[list[object]] = []
    thread_message_repo = MagicMock()
    thread_message_repo.append_if_ready.side_effect = lambda _thread_id, inputs: appended.append(
        list(inputs)
    )
    thread_registry = MagicMock()
    thread_registry.get_bound_thread_id = MagicMock(return_value="thr1")
    thread_registry.get_thread = MagicMock(return_value=None)
    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(get=MagicMock(return_value=SimpleNamespace(user_id=1, kind=None))),
        user_repo=MagicMock(get=MagicMock(return_value=SimpleNamespace(locale="zh"))),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        thread_message_repo=thread_message_repo,
        hitl=coordinator,
    )
    agent_manager.octop_config = SimpleNamespace(default_timezone="Asia/Shanghai")
    _ = [event async for event in processor(_phrase_message("本对话都允许"))]
    assert appended
    duration = None
    for item in appended[0]:
        wire = json.loads(item.message_json)
        data = wire.get("data") if isinstance(wire, dict) else None
        extra = data.get("additional_kwargs") if isinstance(data, dict) else None
        if isinstance(extra, dict) and isinstance(extra.get("turn_duration_ms"), int):
            duration = extra["turn_duration_ms"]
    assert isinstance(duration, int)
    assert duration >= 0


@pytest.mark.asyncio
async def test_sticky_policy_rolls_back_when_member_job_is_gone() -> None:
    from octop.infra.gateway.hitl.phrases import ApprovalUtterance

    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    record = store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    record.resume_agent_id = "member"
    record.resume_thread_id = "thr1~member"
    coordinator.session_policies.set("thr1", {"mode": "allow_tools", "tools": ["write_file"]})

    async for _ in coordinator.iter_utterance_resolution(
        ApprovalUtterance(kind="all"),
        _approval_ctx(),
        agent_manager=MagicMock(),
        locale="zh",
        member_hitl=lambda _pending_id, _decisions: False,
    ):
        pass
    restored = coordinator.session_policies.get("thr1")
    assert restored.mode == "allow_tools"
    assert restored.tools == ("write_file",)
    assert coordinator.session_policies.get("thr1~member").mode == "ask"


@pytest.mark.asyncio
async def test_cli_phrase_approves_without_starting_a_new_turn() -> None:
    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    resumed: list[list[dict[str, str]]] = []

    async def _resume(_agent_id: str, _thread_id: str, decisions: list[dict[str, str]]):
        resumed.append(decisions)
        yield {"type": "token", "content": "done", "node": "agent"}

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _resume
    processor, _registry = _phrase_processor(coordinator, agent_manager)
    chunks = [chunk async for chunk in processor.iter_turn_chunks(_phrase_message("本对话都允许"))]
    assert resumed == [[{"type": "approve"}]]
    assert agent_manager.stream.called is False
    assert coordinator.session_policies.get("thr1").mode == "allow_all"
    assert store.resolve_for_session("sk1") is None
    assert any(chunk.get("type") == "done" for chunk in chunks)
    text = "".join(str(chunk.get("content") or "") for chunk in chunks)
    assert "自动通过" in text


@pytest.mark.asyncio
async def test_reset_phrase_clears_bypass_and_leaves_pending() -> None:
    store = HitlPendingStore()
    coordinator = HitlChannelCoordinator(store=store)
    coordinator.session_policies.set("thr1", {"mode": "allow_all"})
    coordinator.session_policies.set("thr1~member", {"mode": "allow_all"})
    store.register(
        thread_id="thr1",
        agent_id="agent1",
        user_id=1,
        session_key="sk1",
        channel_type="feishu",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    agent_manager = MagicMock()
    processor, _registry = _phrase_processor(coordinator, agent_manager)
    events = [ev async for ev in processor(_phrase_message("恢复每次审批"))]
    assert agent_manager.resume_hitl.called is False
    assert agent_manager.stream.called is False
    assert coordinator.session_policies.get("thr1").mode == "ask"
    assert coordinator.session_policies.get("thr1~member").mode == "ask"
    assert store.resolve_for_session("sk1") is not None
    assert "当前这条" in _event_text(events)


@pytest.mark.asyncio
async def test_reset_phrase_without_pending_clears_bypass() -> None:
    coordinator = HitlChannelCoordinator()
    coordinator.session_policies.set("thr1", {"mode": "allow_all"})
    agent_manager = MagicMock()
    processor, _registry = _phrase_processor(coordinator, agent_manager)
    events = [ev async for ev in processor(_phrase_message("ask again"))]
    assert agent_manager.stream.called is False
    assert coordinator.session_policies.get("thr1").mode == "ask"
    assert "已恢复为每次审批" in _event_text(events)
