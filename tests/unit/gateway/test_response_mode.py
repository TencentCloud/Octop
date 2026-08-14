"""Tests for external IM response delivery modes."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from harness_gateway.models import (
    FileContent,
    InboundMessage,
    MessageEvent,
    MessageEventType,
    TextContent,
)

from octop.infra.gateway.process.response_mode import (
    collapse_to_invoke_response,
    normalize_channel_response_mode,
    processor_for_response_mode,
)


async def _events(*events: MessageEvent) -> AsyncIterator[MessageEvent]:
    for event in events:
        yield event


@pytest.mark.asyncio
async def test_invoke_discards_progress_before_tool_and_emits_final_once() -> None:
    source = _events(
        MessageEvent.typing(),
        MessageEvent.delta("我先查一下。"),
        MessageEvent.flush(),
        MessageEvent.tool_start("web_fetch"),
        MessageEvent.tool_end("web_fetch"),
        MessageEvent.delta("这是"),
        MessageEvent.delta("最终答案。"),
        MessageEvent.completed(),
    )

    result = [event async for event in collapse_to_invoke_response(source)]

    assert [event.type for event in result] == [
        MessageEventType.MESSAGE,
        MessageEventType.COMPLETED,
    ]
    text = result[0].content[0]
    assert isinstance(text, TextContent)
    assert text.text == "这是最终答案。"


@pytest.mark.asyncio
async def test_invoke_preserves_tool_media_with_final_text() -> None:
    attachment = FileContent(filename="report.pdf", data="cGRm")
    source = _events(
        MessageEvent.tool_start("write_file"),
        MessageEvent.tool_end("write_file"),
        MessageEvent(type=MessageEventType.MESSAGE, content=[attachment]),
        MessageEvent.delta("报告已生成。"),
        MessageEvent.completed(),
    )

    result = [event async for event in collapse_to_invoke_response(source)]

    assert result[0].type == MessageEventType.MESSAGE
    assert len(result[0].content) == 2
    assert isinstance(result[0].content[0], TextContent)
    assert result[0].content[1] is attachment


@pytest.mark.asyncio
async def test_invoke_forwards_error_without_partial_text() -> None:
    error = MessageEvent.error_event("upstream failed")
    source = _events(
        MessageEvent.delta("partial"),
        error,
        MessageEvent.completed(),
    )

    result = [event async for event in collapse_to_invoke_response(source)]

    assert result == [error, MessageEvent.completed()]


def test_response_mode_defaults_to_invoke_and_accepts_stream() -> None:
    assert normalize_channel_response_mode(None) == "invoke"
    assert normalize_channel_response_mode("unknown") == "invoke"
    assert normalize_channel_response_mode(" STREAM ") == "stream"


def test_stream_mode_uses_original_processor() -> None:
    async def processor(_message: InboundMessage) -> AsyncIterator[MessageEvent]:
        yield MessageEvent.completed()

    assert processor_for_response_mode(processor, "stream") is processor
    assert processor_for_response_mode(processor, "invoke") is not processor
