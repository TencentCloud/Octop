"""Tests for external IM response delivery modes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from octop_gateway.models import (
    FileContent,
    InboundMessage,
    MessageEvent,
    MessageEventType,
    TextContent,
)
from octop_gateway.utils import close_event_stream

from octop.infra.gateway.process.response_mode import (
    collapse_to_invoke_response,
    normalize_channel_response_mode,
    processor_for_response_mode,
    qq_channel_response_mode,
    withhold_pretool_stream_chunks,
    withhold_weixin_stream_preamble,
    wrap_weixin_stream_processor,
)


def _raw_call(name: str, index: int = 0, call_id: str = "call-1") -> dict[str, Any]:
    return {"type": "tool_call_chunk", "name": name, "index": index, "id": call_id}


def _raw_result(name: str | None, call_id: str = "call-1") -> dict[str, Any]:
    return {
        "type": "tool_result",
        "messages": [ToolMessage(content="ok", name=name, tool_call_id=call_id)],
    }


def _raw_text(text: str) -> dict[str, Any]:
    return {"type": "token", "content": text, "node": "agent_main"}


@pytest.mark.parametrize(
    "chunks,expected",
    [
        pytest.param(
            [_raw_text("English final"), {"type": "delta", "text": "中文"}],
            "English final中文",
            id="no-tools",
        ),
        pytest.param(
            [
                _raw_text("progress"),
                _raw_call("current_time"),
                _raw_result("current_time"),
                _raw_text("final"),
            ],
            "final",
            id="ordinary-tool",
        ),
        pytest.param(
            [
                _raw_text("first"),
                _raw_call("ls"),
                _raw_result("ls"),
                _raw_text("second"),
                _raw_call("cronjob_list", call_id="call-2"),
                _raw_result("cronjob_list", "call-2"),
                _raw_text("final"),
            ],
            "final",
            id="successive-tools",
        ),
        pytest.param(
            [
                _raw_text("dispatch"),
                _raw_call("ask_agent"),
                _raw_result("ask_agent"),
                _raw_text("final"),
            ],
            "dispatchfinal",
            id="team-dispatch",
        ),
        pytest.param(
            [
                _raw_text("dispatch"),
                _raw_call("ask_"),
                _raw_call("agent", call_id=""),
                _raw_result(None),
                _raw_text("final"),
            ],
            "dispatchfinal",
            id="fragmented-name",
        ),
        pytest.param(
            [
                _raw_text("dispatch"),
                _raw_call("ask_"),
                _raw_result("ask_agent"),
                _raw_text("final"),
            ],
            "dispatchfinal",
            id="result-completes-name",
        ),
        pytest.param(
            [
                _raw_text("progress"),
                _raw_call("ask_agent"),
                _raw_call("ls", index=1, call_id="call-2"),
                _raw_result("ask_agent"),
                _raw_result("ls", "call-2"),
                _raw_text("final"),
            ],
            "final",
            id="mixed-parallel-tools",
        ),
        pytest.param(
            [
                _raw_text("progress"),
                _raw_call("ask_agent"),
                _raw_call("ls", index=1, call_id="call-2"),
                _raw_result(None, "call-2"),
                _raw_result(None),
                _raw_text("final"),
            ],
            "final",
            id="parallel-result-ids",
        ),
        pytest.param(
            [_raw_text("progress"), _raw_result("ls"), _raw_text("final")],
            "final",
            id="result-without-call-chunks",
        ),
        pytest.param(
            [
                _raw_text("dispatch"),
                {"type": "tool_result", "name": "ask_agent"},
                _raw_text("final"),
            ],
            "dispatchfinal",
            id="chunk-name-fallback",
        ),
        pytest.param(
            [_raw_text("progress"), {"type": "tool_result"}, _raw_text("final")],
            "final",
            id="unknown-tool",
        ),
        pytest.param(
            [
                _raw_text("progress"),
                _raw_call("ls"),
                _raw_result("ls"),
                _raw_text("final"),
                _raw_result("ls"),
            ],
            "final",
            id="result-replay-after-answer",
        ),
        pytest.param(
            [
                _raw_text("dispatch"),
                _raw_call("ask_agent"),
                _raw_result("ask_agent"),
                _raw_call("ls", call_id="call-2"),
                _raw_result("ls", "call-2"),
                _raw_text("final"),
            ],
            "dispatchfinal",
            id="preserve-approved-dispatch",
        ),
        pytest.param([_raw_text("progress"), _raw_call("ls")], "", id="unfinished-tool-call"),
        pytest.param(
            [
                _raw_text("progress"),
                _raw_call("ask_agent"),
                _raw_result("ask_agent"),
                {"type": "error", "message": "failed"},
            ],
            "",
            id="error-clears-pending-dispatch",
        ),
        pytest.param(
            [_raw_text("progress"), {"type": "hitl_required", "request": {}}],
            "",
            id="hitl-clears-pending",
        ),
        pytest.param(
            [
                _raw_text("progress"),
                _raw_call("ask_agent"),
                {
                    "type": "tool_result",
                    "messages": [
                        {"role": "tool", "name": "ls", "tool_call_id": "historical"},
                        {"role": "tool", "name": "ask_agent", "tool_call_id": "call-1"},
                    ],
                },
                _raw_text("final"),
            ],
            "progressfinal",
            id="history-replay-alongside-live-result",
        ),
        pytest.param(
            [
                _raw_text("dispatch"),
                {"type": "tool_call_chunk", "id": "call-1", "name": "ask_"},
                {"type": "tool_call_chunk", "id": "call-1", "name": "agent"},
                _raw_result(None),
                _raw_text("final"),
            ],
            "dispatchfinal",
            id="id-without-index",
        ),
    ],
)
@pytest.mark.asyncio
async def test_raw_stream_withholds_each_pretool_segment(
    chunks: list[dict[str, Any]], expected: str
) -> None:
    async def stream():
        for chunk in chunks:
            yield chunk

    output = [chunk async for chunk in withhold_pretool_stream_chunks(stream())]

    assert (
        "".join(
            str(c.get("content") or c.get("text") or "")
            for c in output
            if c["type"] in {"token", "delta"}
        )
        == expected
    )
    original_control = [c for c in chunks if c["type"] not in {"token", "delta"}]
    output_control = [c for c in output if c["type"] not in {"token", "delta"}]
    assert len(output_control) == len(original_control)
    assert all(a is b for a, b in zip(output_control, original_control, strict=True))


@pytest.mark.parametrize("terminal", ["error", "hitl_required", "cancel"])
@pytest.mark.asyncio
async def test_raw_preamble_filter_closes_source(terminal: str) -> None:
    closed = False

    async def stream():
        nonlocal closed
        try:
            yield _raw_text("pending")
            yield {"type": terminal}
            await asyncio.Event().wait()
        finally:
            closed = True

    filtered = withhold_pretool_stream_chunks(stream())
    assert (await anext(filtered))["type"] == terminal
    await close_event_stream(filtered)
    assert closed


@pytest.mark.asyncio
async def test_raw_preamble_filter_resolves_name_without_streamed_call_id() -> None:
    async def stream():
        yield _raw_text("dispatch")
        yield _raw_call("ask_", call_id="")
        yield _raw_result("ask_agent")
        yield _raw_text("final")

    output = [c async for c in withhold_pretool_stream_chunks(stream())]
    assert [c["content"] for c in output if c["type"] == "token"] == ["dispatch", "final"]


@pytest.mark.asyncio
async def test_raw_preamble_filter_keeps_parallel_team_dispatch() -> None:
    async def stream():
        yield _raw_text("dispatch")
        yield _raw_call("ask_", call_id="call-1")
        yield _raw_call("ask_", index=1, call_id="call-2")
        yield _raw_call("agent", call_id="")
        yield _raw_call("agent", index=1, call_id="")
        yield _raw_result(None, "call-2")
        yield _raw_result(None, "call-1")
        yield _raw_text("final")

    output = [c async for c in withhold_pretool_stream_chunks(stream())]
    assert [c["content"] for c in output if c["type"] == "token"] == ["dispatch", "final"]


@pytest.mark.asyncio
async def test_raw_preamble_filter_passes_usage_reasoning_and_state_unchanged() -> None:
    control = [
        {"type": "usage", "usage": {"output_tokens": 10}},
        {"type": "reasoning", "content": "private"},
        {"type": "state_snapshot", "data": {"messages": []}},
    ]

    async def stream():
        yield _raw_text("answer")
        for chunk in control:
            yield chunk

    output = [chunk async for chunk in withhold_pretool_stream_chunks(stream())]
    assert output[:-1] == control
    assert output[-1]["content"] == "answer"


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

    assert result == [error]


@pytest.mark.parametrize("mode", ["invoke", "weixin-stream"])
async def test_terminal_error_closes_underlying_processor_through_response_wrapper(mode):
    closed = False

    async def source(_message):
        nonlocal closed
        try:
            yield MessageEvent.error_event("simulated failure")
            await asyncio.Event().wait()
        finally:
            closed = True

    processor = (
        processor_for_response_mode(source, "invoke")
        if mode == "invoke"
        else wrap_weixin_stream_processor(source)
    )
    stream = processor(InboundMessage(channel_id="test", content=[TextContent(text="test")]))
    assert (await anext(stream)).type == MessageEventType.ERROR
    await close_event_stream(stream)
    assert closed


@pytest.mark.asyncio
async def test_invoke_keeps_ask_agent_dispatch_narration() -> None:
    """Team hosts often narrate before ask_agent — keep that line on invoke IM."""
    source = _events(
        MessageEvent.delta("我先请临床助手看一下。"),
        MessageEvent.tool_start("咨询专家", tool_key="ask_agent"),
        MessageEvent.tool_end("咨询专家"),
        MessageEvent.completed(),
    )

    result = [event async for event in collapse_to_invoke_response(source)]

    assert [event.type for event in result] == [
        MessageEventType.MESSAGE,
        MessageEventType.COMPLETED,
    ]
    text = result[0].content[0]
    assert isinstance(text, TextContent)
    assert text.text == "我先请临床助手看一下。"


@pytest.mark.asyncio
async def test_invoke_still_discards_progress_before_other_tools() -> None:
    source = _events(
        MessageEvent.delta("我先查一下。"),
        MessageEvent.tool_start("web_fetch", tool_key="web_fetch"),
        MessageEvent.tool_end("web_fetch"),
        MessageEvent.delta("最终答案。"),
        MessageEvent.completed(),
    )

    result = [event async for event in collapse_to_invoke_response(source)]
    text = result[0].content[0]
    assert isinstance(text, TextContent)
    assert text.text == "最终答案。"


def test_response_mode_defaults_to_invoke_and_accepts_stream() -> None:
    assert normalize_channel_response_mode(None) == "invoke"
    assert normalize_channel_response_mode("unknown") == "invoke"
    assert normalize_channel_response_mode(" STREAM ") == "stream"


def test_stream_mode_uses_original_processor() -> None:
    async def processor(_message: InboundMessage) -> AsyncIterator[MessageEvent]:
        yield MessageEvent.completed()

    assert processor_for_response_mode(processor, "stream") is processor
    assert processor_for_response_mode(processor, "invoke") is not processor


@pytest.mark.asyncio
async def test_weixin_stream_drops_preamble_but_keeps_ask_agent() -> None:
    source = _events(
        MessageEvent.delta("我先查一下。"),
        MessageEvent.flush(),
        MessageEvent.tool_start("web_fetch", tool_key="web_fetch"),
        MessageEvent.delta("结果"),
        MessageEvent.tool_start("ask_agent", tool_key="ask_agent"),
        MessageEvent.completed(),
    )
    result = [event async for event in withhold_weixin_stream_preamble(source)]
    texts = [
        part.text
        for event in result
        if event.type == MessageEventType.DELTA
        for part in event.content
        if isinstance(part, TextContent)
    ]
    assert "我先查一下。" not in texts
    assert "结果" in texts
    assert any(
        event.type == MessageEventType.TOOL_START and event.metadata.get("tool_key") == "ask_agent"
        for event in result
    )


def test_newer_weixin_token_is_kept() -> None:
    from octop.infra.utils.weixin_context import (
        WEIXIN_CONTEXT_TOKEN_KEY,
        WEIXIN_CONTEXT_TOKEN_MS_KEY,
        merge_weixin_context_token,
    )

    kept = merge_weixin_context_token(
        {WEIXIN_CONTEXT_TOKEN_KEY: "new", WEIXIN_CONTEXT_TOKEN_MS_KEY: 20, "account_id": "a"},
        {WEIXIN_CONTEXT_TOKEN_KEY: "old", WEIXIN_CONTEXT_TOKEN_MS_KEY: 10, "account_id": "b"},
    )
    assert kept[WEIXIN_CONTEXT_TOKEN_KEY] == "new"
    assert kept["account_id"] == "b"

    empty = merge_weixin_context_token(
        {WEIXIN_CONTEXT_TOKEN_KEY: "keep", WEIXIN_CONTEXT_TOKEN_MS_KEY: 5, "account_id": "a"},
        {"account_id": "a"},
    )
    assert empty[WEIXIN_CONTEXT_TOKEN_KEY] == "keep"


def test_qq_channel_streams_by_default() -> None:
    assert qq_channel_response_mode({}) == "stream"
    assert qq_channel_response_mode({"response_mode": "invoke"}) == "stream"
    assert qq_channel_response_mode({"streaming": False}) == "stream"
    assert qq_channel_response_mode({"c2c_streaming": True}) == "stream"
    assert qq_channel_response_mode({"c2c_streaming": False}) == "invoke"
    assert qq_channel_response_mode({"c2c_streaming": "false"}) == "invoke"
