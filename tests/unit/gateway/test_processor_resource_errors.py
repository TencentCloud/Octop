"""Resource-policy stream error projection tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from harness_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.process.history_projection import _wire_text
from octop.infra.gateway.process.processor import GlobalProcessor, _stream_error
from octop.infra.gateway.slash.dispatcher import SlashDispatcher
from octop.infra.gateway.ws import WS_CHANNEL_ID


def test_stream_error_preserves_resource_error_code() -> None:
    error = OctopError(
        ErrorCode.TOKEN_QUOTA_EXCEEDED,
        "token quota exceeded",
        details={"used": 12, "quota": 10},
    )

    message, code = _stream_error(error, "zh")

    assert code == "TOKEN_QUOTA_EXCEEDED"
    assert "12/10" in message


def _processor_with_stream(
    stream: Callable[..., AsyncIterator[dict[str, Any]]],
) -> tuple[GlobalProcessor, InboundMessage, list[list[Any]]]:
    appended: list[list[Any]] = []

    agent_manager = MagicMock()
    agent_manager.stream = stream
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])

    agent_row = MagicMock()
    agent_row.user_id = 1
    agent_row.config_json = "{}"
    agent_row.system_prompt = None
    agent_row.default_model = None
    agent_repo = MagicMock()
    agent_repo.get = MagicMock(return_value=agent_row)

    thread_message_repo = MagicMock()
    thread_message_repo.append_if_ready.side_effect = lambda _thread_id, inputs: (
        appended.append(list(inputs)) or len(inputs)
    )

    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=agent_repo,
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=None,
        thread_message_repo=thread_message_repo,
    )
    processor._record_stream_error = AsyncMock()
    msg = InboundMessage(
        channel_id=WS_CHANNEL_ID,
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="continue this")],
        metadata={"session_key": "sk", "thread_id": "thread-1"},
    )
    return processor, msg, appended


@pytest.mark.asyncio
async def test_iter_turn_chunks_persists_partial_output_and_error() -> None:
    async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "token", "content": "partial answer"}
        raise RuntimeError("Error code: 402 insufficient balance")

    processor, msg, appended = _processor_with_stream(stream)
    chunks = [chunk async for chunk in processor.iter_turn_chunks(msg)]

    assert any(chunk.get("type") == "error" for chunk in chunks)
    assert chunks[-1]["type"] == "done"
    assert appended
    texts = [_wire_text(item) for item in appended[0]]
    assert any("continue this" in text for text in texts)
    assert "partial answer" in texts
    assert any("余额" in text or "insufficient" in text.lower() for text in texts)
    assert any(
        json.loads(item.message_json)["data"]["additional_kwargs"].get("octop_stream_error")
        for item in appended[0]
        if "余额" in _wire_text(item) or "insufficient" in _wire_text(item).lower()
    )
    processor._thread_registry.touch_last_active.assert_called_with("thread-1")


@pytest.mark.asyncio
async def test_iter_turn_chunks_persists_streamed_tokens_without_state() -> None:
    async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "token", "content": "partial answer"}

    processor, msg, appended = _processor_with_stream(stream)
    chunks = [chunk async for chunk in processor.iter_turn_chunks(msg)]

    assert not any(chunk.get("type") == "error" for chunk in chunks)
    assert chunks[-1]["type"] == "done"
    texts = [_wire_text(item) for item in appended[0]]
    assert any("continue this" in text for text in texts)
    assert "partial answer" in texts


@pytest.mark.asyncio
async def test_iter_turn_chunks_persists_partial_when_cancelled() -> None:
    async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "token", "content": "partial answer"}
        raise asyncio.CancelledError

    processor, msg, appended = _processor_with_stream(stream)
    with pytest.raises(asyncio.CancelledError):
        _ = [chunk async for chunk in processor.iter_turn_chunks(msg)]

    texts = [_wire_text(item) for item in appended[0]]
    assert any("continue this" in text for text in texts)
    assert "partial answer" in texts
