"""Dashboard HITL resume SSE must persist follow-up approvals in the pending store."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.api.routers.chat.routes import iter_dashboard_hitl_resume_sse
from octop.infra.gateway.hitl.coordinator import HitlChannelCoordinator


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
    assert any(c.get("type") == "hitl_required" for c in chunks)
    assert any(c.get("type") == "done" for c in chunks)

    followup = hitl.store.resolve_pending_for_thread(
        "thr-follow",
        agent_id="agent-1",
        user_id=1,
    )
    assert followup is not None
    assert followup.pending_id != first.pending_id
    assert followup.action_requests[0]["args"]["command"] == "ls -la /private/etc"
    assert hitl.store.get(first.pending_id) is not None
    assert hitl.store.get(first.pending_id).status == "approved"  # type: ignore[union-attr]


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
