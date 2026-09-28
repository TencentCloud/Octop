"""Dashboard HITL resume SSE must persist follow-up approvals in the pending store."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.api.routers.chat.routes import iter_dashboard_hitl_resume_sse
from octop.infra.gateway.hitl.coordinator import HitlChannelCoordinator
from octop.infra.gateway.ws.ws_hub import WebSocketHub


def _parse_sse_chunks(raw: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        data_line = next(
            (line[6:] for line in block.split("\n") if line.startswith("data: ")),
            None,
        )
        if data_line is None:
            continue
        chunks.append(json.loads(data_line))
    return chunks


@pytest.mark.asyncio
async def test_dashboard_hitl_resume_registers_followup_hitl_required() -> None:
    async def _resume(*_args: object, **_kwargs: object):
        yield {"type": "token", "content": "ok"}
        yield {
            "type": "hitl_required",
            "request": {
                "action_requests": [
                    {"name": "execute", "args": {"command": "ls -la /private/etc"}},
                ],
                "review_configs": [
                    {"action_name": "execute", "allowed_decisions": ["approve", "reject"]},
                ],
            },
        }

    processor = MagicMock()
    processor.iter_hitl_resume_chunks = _resume
    hitl = HitlChannelCoordinator()
    first = hitl.store.register(
        thread_id="thr-follow",
        agent_id="agent-1",
        user_id=1,
        session_key="agent-1:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=[{"name": "execute", "args": {"command": "ls -la /etc"}}],
        review_configs=None,
    )

    frames: list[str] = []
    async for frame in iter_dashboard_hitl_resume_sse(
        server=object(),
        processor=processor,
        hitl_coordinator=hitl,
        agent_id="agent-1",
        thread_id="thr-follow",
        user_id=1,
        decisions=[{"type": "approve"}],
        pending=first,
        session_key="agent-1:dashboard:1:dm",
        channel_type="dashboard",
        locale="zh",
        is_disconnected=AsyncMock(return_value=False),
    ):
        frames.append(frame)

    chunks = _parse_sse_chunks("".join(frames))
    hitl_chunks = [c for c in chunks if c.get("type") == "hitl_required"]
    assert hitl_chunks
    assert chunks[-1] == {"type": "done", "hitl_paused": True}

    followup = hitl.store.resolve_pending_for_thread(
        "thr-follow",
        agent_id="agent-1",
        user_id=1,
    )
    assert followup is not None
    assert hitl_chunks[0]["request"]["pending_id"] == followup.pending_id
    assert followup.pending_id != first.pending_id
    assert followup.action_requests[0]["args"]["command"] == "ls -la /private/etc"
    assert hitl.store.get(first.pending_id) is not None
    assert hitl.store.get(first.pending_id).status == "approved"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_dashboard_hitl_resume_wakes_team_member_without_host_resume() -> None:
    from types import SimpleNamespace

    hitl = HitlChannelCoordinator()
    pending = hitl.store.register(
        thread_id="thr-room",
        agent_id="host",
        user_id=1,
        session_key="host:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=[{"name": "execute", "args": {"command": "df"}}],
        review_configs=None,
    )
    pending.resume_agent_id = "member"
    pending.resume_thread_id = "thr-room~member"
    delivered: dict[str, object] = {}

    def deliver(pending_id: str, decisions: list[dict[str, str]]) -> bool:
        delivered["id"] = pending_id
        delivered["decisions"] = decisions
        return True

    processor = SimpleNamespace(teams=SimpleNamespace(deliver_member_hitl=deliver))
    frames: list[str] = []
    async for frame in iter_dashboard_hitl_resume_sse(
        server=object(),
        processor=processor,
        hitl_coordinator=hitl,
        agent_id="host",
        thread_id="thr-room",
        user_id=1,
        decisions=[{"type": "approve"}],
        pending=pending,
        session_key="host:dashboard:1:dm",
        channel_type="dashboard",
        locale="zh",
        is_disconnected=AsyncMock(return_value=False),
    ):
        frames.append(frame)

    chunks = _parse_sse_chunks("".join(frames))
    assert chunks == [{"type": "done", "team_member_continuing": True}]
    assert delivered == {"id": pending.pending_id, "decisions": [{"type": "approve"}]}
    assert hitl.store.get(pending.pending_id) is not None
    assert hitl.store.get(pending.pending_id).status == "approved"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_dashboard_hitl_resume_expires_when_member_job_is_gone() -> None:
    from types import SimpleNamespace

    hitl = HitlChannelCoordinator()
    pending = hitl.store.register(
        thread_id="thr-room",
        agent_id="host",
        user_id=1,
        session_key="host:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=[{"name": "execute", "args": {}}],
        review_configs=None,
    )
    pending.resume_agent_id = "member"
    pending.resume_thread_id = "thr-room~member"
    processor = SimpleNamespace(
        teams=SimpleNamespace(deliver_member_hitl=lambda *_args, **_kwargs: False)
    )
    frames: list[str] = []
    async for frame in iter_dashboard_hitl_resume_sse(
        server=object(),
        processor=processor,
        hitl_coordinator=hitl,
        agent_id="host",
        thread_id="thr-room",
        user_id=1,
        decisions=[{"type": "reject"}],
        pending=pending,
        session_key="host:dashboard:1:dm",
        channel_type="dashboard",
        locale="en",
        is_disconnected=AsyncMock(return_value=False),
    ):
        frames.append(frame)

    chunks = _parse_sse_chunks("".join(frames))
    assert chunks[0]["type"] == "error"
    assert "expired" in chunks[0]["message"].lower()
    assert hitl.store.get(pending.pending_id) is not None
    assert hitl.store.get(pending.pending_id).status == "expired"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_dashboard_hitl_resume_registers_without_prior_pending() -> None:
    async def _resume(*_args: object, **_kwargs: object):
        yield {
            "type": "hitl_required",
            "request": {
                "action_requests": [{"name": "execute", "args": {"command": "echo hi"}}],
            },
        }

    processor = MagicMock()
    processor.iter_hitl_resume_chunks = _resume
    hitl = HitlChannelCoordinator()

    async for _ in iter_dashboard_hitl_resume_sse(
        server=object(),
        processor=processor,
        hitl_coordinator=hitl,
        agent_id="agent-1",
        thread_id="thr-orphan",
        user_id=9,
        decisions=[{"type": "approve"}],
        pending=None,
        session_key="sk-orphan",
        channel_type="dashboard",
        locale="en",
        is_disconnected=AsyncMock(return_value=False),
    ):
        pass

    pending = hitl.store.resolve_pending_for_thread(
        "thr-orphan",
        agent_id="agent-1",
        user_id=9,
    )
    assert pending is not None
    assert pending.action_requests[0]["args"]["command"] == "echo hi"


@pytest.mark.asyncio
async def test_dashboard_hitl_resume_finishes_after_client_disconnect() -> None:
    completed = False

    async def _resume(*_args: object, **_kwargs: object):
        nonlocal completed
        yield {"type": "token", "content": "hidden after disconnect"}
        completed = True

    processor = MagicMock()
    processor.iter_hitl_resume_chunks = _resume
    hitl = HitlChannelCoordinator()

    frames = [
        frame
        async for frame in iter_dashboard_hitl_resume_sse(
            server=object(),
            processor=processor,
            hitl_coordinator=hitl,
            agent_id="agent-1",
            thread_id="thr-disconnected",
            user_id=9,
            decisions=[{"type": "respond", "message": "answer"}],
            pending=None,
            session_key="sk-disconnected",
            channel_type="dashboard",
            locale="en",
            is_disconnected=AsyncMock(return_value=True),
        )
    ]

    assert completed is True
    assert frames == []


@pytest.mark.asyncio
async def test_dashboard_hitl_resume_broadcasts_to_thread_subscribers() -> None:
    """A page open on the thread sees the remote resolution live (no reload)."""

    async def _resume(*_args: object, **_kwargs: object):
        yield {"type": "token", "content": "resuming"}
        yield {"type": "state_snapshot", "data": {"messages": []}}

    processor = MagicMock()
    processor.iter_hitl_resume_chunks = _resume
    hitl = HitlChannelCoordinator()
    hub = WebSocketHub()

    received: list[dict[str, Any]] = []

    async def _send(frame: dict[str, Any]) -> None:
        received.append(frame)

    hub.register("conn-open-page", _send)
    hub.subscribe("thr-open", "conn-open-page")

    async for _ in iter_dashboard_hitl_resume_sse(
        server=object(),
        processor=processor,
        hitl_coordinator=hitl,
        agent_id="agent-1",
        thread_id="thr-open",
        user_id=1,
        decisions=[{"type": "approve"}],
        pending=None,
        session_key="sk-open",
        channel_type="dashboard",
        locale="en",
        is_disconnected=AsyncMock(return_value=False),
        hub=hub,
    ):
        pass

    assert [c["type"] for c in received] == ["token", "state_snapshot", "done"]
    assert hub.is_turn_active("thr-open") is False


@pytest.mark.asyncio
async def test_dashboard_hitl_resume_broadcasts_after_client_disconnect() -> None:
    """Subscribers keep receiving frames even once the SSE client is gone."""

    async def _resume(*_args: object, **_kwargs: object):
        yield {"type": "token", "content": "still running"}

    processor = MagicMock()
    processor.iter_hitl_resume_chunks = _resume
    hitl = HitlChannelCoordinator()
    hub = WebSocketHub()

    received: list[dict[str, Any]] = []

    async def _send(frame: dict[str, Any]) -> None:
        received.append(frame)

    hub.register("conn-open-page", _send)
    hub.subscribe("thr-gone", "conn-open-page")

    frames = [
        frame
        async for frame in iter_dashboard_hitl_resume_sse(
            server=object(),
            processor=processor,
            hitl_coordinator=hitl,
            agent_id="agent-1",
            thread_id="thr-gone",
            user_id=1,
            decisions=[{"type": "approve"}],
            pending=None,
            session_key="sk-gone",
            channel_type="dashboard",
            locale="en",
            is_disconnected=AsyncMock(return_value=True),
            hub=hub,
        )
    ]

    assert frames == []
    assert [c["type"] for c in received] == ["token", "done"]


@pytest.mark.asyncio
async def test_dashboard_hitl_resume_broadcasts_followup_pause_to_subscribers() -> None:
    """A follow-up HITL pause mid-resume also reaches WS subscribers.

    The hitl_required chunk must carry the enriched ``request`` (pending_id)
    and the turn must end with ``done`` + ``hitl_paused``, not a plain done.
    """

    async def _resume(*_args: object, **_kwargs: object):
        yield {"type": "token", "content": "checking"}
        yield {
            "type": "hitl_required",
            "request": {
                "action_requests": [
                    {"name": "execute", "args": {"command": "ls -la /tmp"}},
                ],
                "review_configs": [
                    {"action_name": "execute", "allowed_decisions": ["approve", "reject"]},
                ],
            },
        }

    processor = MagicMock()
    processor.iter_hitl_resume_chunks = _resume
    hitl = HitlChannelCoordinator()
    hub = WebSocketHub()

    received: list[dict[str, Any]] = []

    async def _send(frame: dict[str, Any]) -> None:
        received.append(frame)

    hub.register("conn-open-page", _send)
    hub.subscribe("thr-pause", "conn-open-page")

    async for _ in iter_dashboard_hitl_resume_sse(
        server=object(),
        processor=processor,
        hitl_coordinator=hitl,
        agent_id="agent-1",
        thread_id="thr-pause",
        user_id=1,
        decisions=[{"type": "approve"}],
        pending=None,
        session_key="sk-pause",
        channel_type="dashboard",
        locale="en",
        is_disconnected=AsyncMock(return_value=False),
        hub=hub,
    ):
        pass

    assert [c["type"] for c in received] == ["token", "hitl_required", "done"]
    assert received[-1]["hitl_paused"] is True
    assert received[1]["request"]["pending_id"]
    assert hub.is_turn_active("thr-pause") is False


@pytest.mark.asyncio
async def test_dashboard_hitl_resume_marks_pending_resolved_when_stream_errors() -> None:
    async def _resume(*_args: object, **_kwargs: object):
        raise RuntimeError("stream died")
        yield {}  # pragma: no cover

    processor = MagicMock()
    processor.iter_hitl_resume_chunks = _resume
    hitl = HitlChannelCoordinator()
    first = hitl.store.register(
        thread_id="thr-err",
        agent_id="agent-1",
        user_id=1,
        session_key="sk-err",
        channel_type="dashboard",
        action_requests=[{"name": "ask_user_question", "args": {"questions": []}}],
        review_configs=None,
    )

    frames: list[str] = []
    async for frame in iter_dashboard_hitl_resume_sse(
        server=object(),
        processor=processor,
        hitl_coordinator=hitl,
        agent_id="agent-1",
        thread_id="thr-err",
        user_id=1,
        decisions=[{"type": "respond", "message": "ok"}],
        pending=first,
        session_key="sk-err",
        channel_type="dashboard",
        locale="zh",
        is_disconnected=AsyncMock(return_value=False),
    ):
        frames.append(frame)

    chunks = _parse_sse_chunks("".join(frames))
    assert any(c.get("type") == "error" for c in chunks)
    resolved = hitl.store.get(first.pending_id)
    assert resolved is not None
    assert resolved.status == "expired"
    assert hitl.store.resolve_pending_for_thread("thr-err", agent_id="agent-1", user_id=1) is None
