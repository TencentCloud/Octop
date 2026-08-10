"""Unit tests for IM channel HITL."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from harness_gateway.models import MessageEvent, MessageEventType, TextContent

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
    assert "ab12" in text


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

    from harness_agent.slash import SlashCommand

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

    from harness_agent.slash import SlashCommand

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

    from harness_agent.slash import SlashCommand

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

    from harness_agent.slash import SlashCommand

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
