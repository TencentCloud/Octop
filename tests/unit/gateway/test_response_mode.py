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
async def test_invoke_strips_orphan_thinking_prefix_from_final_text() -> None:
    source = _events(
        MessageEvent.delta("Let me inspect another source. "),
        MessageEvent.delta("This is internal reasoning."),
        MessageEvent.delta("</think>"),
        MessageEvent.delta("【每日指南学习】最终内容"),
        MessageEvent.completed(),
    )

    result = [event async for event in collapse_to_invoke_response(source)]

    assert [event.type for event in result] == [
        MessageEventType.MESSAGE,
        MessageEventType.COMPLETED,
    ]
    text = result[0].content[0]
    assert isinstance(text, TextContent)
    assert text.text == "【每日指南学习】最终内容"


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


@pytest.mark.asyncio
async def test_invoke_silent_marker_suppresses_final_message() -> None:
    source = _events(
        MessageEvent.delta("这个结论不用发给用户"),
        MessageEvent.delta(" NO_REPLY"),
        MessageEvent.completed(),
    )

    result = [event async for event in collapse_to_invoke_response(source)]

    assert result == [MessageEvent.completed()]


@pytest.mark.asyncio
async def test_invoke_silent_marker_suppresses_media_too() -> None:
    attachment = FileContent(filename="report.pdf", data="cGRm")
    source = _events(
        MessageEvent.tool_start("write_file"),
        MessageEvent.tool_end("write_file"),
        MessageEvent(type=MessageEventType.MESSAGE, content=[attachment]),
        MessageEvent.delta("文件已生成,但无需推送 SKIP。"),
        MessageEvent.completed(),
    )

    result = [event async for event in collapse_to_invoke_response(source)]

    assert result == [MessageEvent.completed()]


@pytest.mark.asyncio
async def test_invoke_marker_mid_text_still_delivers() -> None:
    source = _events(
        MessageEvent.delta("NO_REPLY 是一个静默标记,但出现在中间时不生效。"),
        MessageEvent.completed(),
    )

    result = [event async for event in collapse_to_invoke_response(source)]

    assert [event.type for event in result] == [
        MessageEventType.MESSAGE,
        MessageEventType.COMPLETED,
    ]
    text = result[0].content[0]
    assert isinstance(text, TextContent)
    assert text.text == "NO_REPLY 是一个静默标记,但出现在中间时不生效。"


def test_stream_mode_uses_original_processor() -> None:
    async def processor(_message: InboundMessage) -> AsyncIterator[MessageEvent]:
        yield MessageEvent.completed()

    assert processor_for_response_mode(processor, "stream") is processor
    assert processor_for_response_mode(processor, "invoke") is not processor


@pytest.mark.asyncio
async def test_stream_mode_bypasses_silent_marker() -> None:
    async def processor(_message: InboundMessage) -> AsyncIterator[MessageEvent]:
        yield MessageEvent.delta("流式通道照常输出 NO_REPLY")
        yield MessageEvent.completed()

    result = [event async for event in processor_for_response_mode(processor, "stream")(None)]

    assert [event.type for event in result] == [
        MessageEventType.DELTA,
        MessageEventType.COMPLETED,
    ]
    text = result[0].content[0]
    assert isinstance(text, TextContent)
    assert text.text == "流式通道照常输出 NO_REPLY"
