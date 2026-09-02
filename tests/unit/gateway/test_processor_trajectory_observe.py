"""GlobalProcessor side-notifies TrajectoryService without changing stream payloads."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from harness_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher
from octop.infra.gateway.ws import WS_CHANNEL_ID

_TOOL_CHUNK = {
    "type": "tool_call_chunk",
    "id": "call_1",
    "name": "read_file",
    "args": {"path": "a.py"},
}


class _RecordingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def observe_chunk(self, agent_id: str, thread_id: str, chunk: dict[str, Any]) -> None:
        self.calls.append((agent_id, thread_id, chunk))


class _BoomService:
    def observe_chunk(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("observe down")


def _processor(*, trajectory_service: object | None) -> GlobalProcessor:
    async def _stream(*_args: object, **_kwargs: object):
        yield dict(_TOOL_CHUNK)

    agent_manager = MagicMock()
    agent_manager.stream = _stream
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])

    return GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=None,
        trajectory_service=trajectory_service,
    )


def _dashboard_msg() -> InboundMessage:
    return InboundMessage(
        channel_id=WS_CHANNEL_ID,
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="read a.py")],
        metadata={"session_key": "sk", "thread_id": "thread-1"},
    )


@pytest.mark.asyncio
async def test_iter_turn_chunks_observes_tool_chunk() -> None:
    service = _RecordingService()
    processor = _processor(trajectory_service=service)

    chunks = [c async for c in processor.iter_turn_chunks(_dashboard_msg())]

    assert any(c.get("type") == "tool_call_chunk" for c in chunks)
    assert chunks[-1]["type"] == "done"
    assert len(service.calls) == 1
    agent_id, thread_id, chunk = service.calls[0]
    assert agent_id == "agent-1"
    assert thread_id == "thread-1"
    assert chunk["type"] == "tool_call_chunk"
    assert chunk["name"] == "read_file"


@pytest.mark.asyncio
async def test_iter_turn_chunks_continues_when_observe_raises() -> None:
    processor = _processor(trajectory_service=_BoomService())

    chunks = [c async for c in processor.iter_turn_chunks(_dashboard_msg())]

    tool = next(c for c in chunks if c.get("type") == "tool_call_chunk")
    assert tool["name"] == "read_file"
    assert chunks[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_iter_turn_chunks_noop_when_service_absent() -> None:
    processor = _processor(trajectory_service=None)

    chunks = [c async for c in processor.iter_turn_chunks(_dashboard_msg())]

    assert any(c.get("type") == "tool_call_chunk" for c in chunks)
    assert chunks[-1]["type"] == "done"
