"""Cron agent delivery must not push pre-tool narration to IM users (#2384)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from octop.infra.cron.stream_filter import withhold_pretool_stream_chunks


async def _run(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    async def _gen() -> AsyncIterator[dict[str, Any]]:
        for chunk in chunks:
            yield chunk

    return [item async for item in withhold_pretool_stream_chunks(_gen())]


def _text_of(out: list[dict[str, Any]]) -> str:
    parts = []
    for chunk in out:
        if chunk.get("type") in ("token", "delta"):
            parts.append(str(chunk.get("content") or chunk.get("text") or ""))
    return "".join(parts)


def _types_of(out: list[dict[str, Any]]) -> list[str]:
    return [str(chunk.get("type")) for chunk in out]


async def test_plain_tool_narration_dropped_final_answer_kept() -> None:
    out = await _run(
        [
            {"type": "token", "content": "I'll start by gathering the time... "},
            {"type": "tool_call_chunk", "index": 0, "name": "cronjob_list", "args": "{}"},
            {"type": "tool_result", "content": "[]"},
            {"type": "token", "content": "今日无任务"},
        ]
    )
    assert _text_of(out) == "今日无任务"
    assert _types_of(out) == ["tool_call_chunk", "tool_result", "token"]


async def test_ask_agent_dispatch_narration_kept() -> None:
    out = await _run(
        [
            {"type": "token", "content": "请成员A查询数据。"},
            {"type": "tool_call_chunk", "index": 0, "name": "ask_agent", "args": "{}"},
            {"type": "tool_result", "content": "ok"},
            {"type": "token", "content": "汇总完成"},
        ]
    )
    assert _text_of(out) == "请成员A查询数据。汇总完成"
    # Held narration is released before the ask_agent chunk, order preserved.
    assert _types_of(out) == ["token", "tool_call_chunk", "tool_result", "token"]


async def test_narration_between_sequential_tools_dropped() -> None:
    out = await _run(
        [
            {"type": "token", "content": "先查列表。"},
            {"type": "tool_call_chunk", "index": 0, "name": "cronjob_list", "args": "{}"},
            {"type": "tool_result", "content": "[]"},
            {"type": "token", "content": "再查时间。"},
            {"type": "tool_call_chunk", "index": 0, "name": "current_time", "args": "{}"},
            {"type": "tool_result", "content": "12:00"},
            {"type": "token", "content": "任务完成，时间 12:00"},
        ]
    )
    assert _text_of(out) == "任务完成，时间 12:00"


async def test_sharded_tool_name_still_recognized() -> None:
    out = await _run(
        [
            {"type": "token", "content": "narration"},
            {"type": "tool_call_chunk", "index": 0, "name": "cron"},
            {"type": "tool_call_chunk", "index": 0, "name": "job_list", "args": "{}"},
            {"type": "tool_result", "content": "[]"},
            {"type": "token", "content": "final"},
        ]
    )
    assert _text_of(out) == "final"


async def test_parallel_tools_drop_narration() -> None:
    out = await _run(
        [
            {"type": "token", "content": "plan"},
            {"type": "tool_call_chunk", "index": 0, "name": "ls", "args": "{}"},
            {"type": "tool_call_chunk", "index": 1, "name": "grep", "args": "{}"},
            {"type": "tool_result", "content": "[]"},
            {"type": "tool_result", "content": "[]"},
            {"type": "token", "content": "done"},
        ]
    )
    assert _text_of(out) == "done"


async def test_tool_result_without_call_chunks_drops_narration() -> None:
    """Replayed results (no streamed call chunks) must still gate the text."""
    out = await _run(
        [
            {"type": "token", "content": "narration"},
            {"type": "tool_result", "content": "[]"},
            {"type": "token", "content": "final"},
        ]
    )
    assert _text_of(out) == "final"


async def test_hitl_required_clears_pending_narration() -> None:
    out = await _run(
        [
            {"type": "token", "content": "我将执行审批操作..."},
            {"type": "hitl_required", "request": {}},
        ]
    )
    assert _text_of(out) == ""
    assert "hitl_required" in _types_of(out)


async def test_no_tool_stream_passes_all_text() -> None:
    out = await _run(
        [
            {"type": "token", "content": "你好，"},
            {"type": "token", "content": "世界"},
        ]
    )
    assert _text_of(out) == "你好，世界"


async def test_delta_kind_text_is_withheld_and_released() -> None:
    out = await _run(
        [
            {"type": "delta", "text": "lead-in"},
            {"type": "tool_call_chunk", "index": 0, "name": "current_time", "args": "{}"},
            {"type": "tool_result", "content": "12:00"},
            {"type": "delta", "text": "answer"},
        ]
    )
    assert _text_of(out) == "answer"


async def test_non_text_chunks_pass_through_untouched() -> None:
    reasoning = {"type": "reasoning", "content": "thinking..."}
    out = await _run(
        [
            {"type": "token", "content": "text"},
            reasoning,
        ]
    )
    assert reasoning in out
    assert _text_of(out) == "text"


async def test_stream_dying_midturn_releases_partial_text() -> None:
    """#516: a stream that dies must still yield its partial text downstream."""

    async def _gen() -> AsyncIterator[dict[str, Any]]:
        yield {"type": "token", "content": "先查一下"}
        raise RuntimeError("tool call failed")

    collected: list[dict[str, Any]] = []
    with_error: BaseException | None = None
    try:
        async for item in withhold_pretool_stream_chunks(_gen()):
            collected.append(item)
    except RuntimeError as exc:
        with_error = exc
    assert with_error is not None
    assert _text_of(collected) == "先查一下"
