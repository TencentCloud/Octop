"""Unit tests for chat polish and history helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from octop.api.routers.chat.serialize import (
    _entry_matches_thread,
    _merge_adjacent_messages,
    _serialize_history_message,
    _strip_thinking,
    _ts_to_ms,
)
from octop.infra.utils.llm_text import llm_text_content as _llm_text_content


def test_serialize_history_message_includes_thinking_and_tools() -> None:
    user = _serialize_history_message(HumanMessage(content="hello"))
    assert user is not None
    assert user["role"] == "user"
    assert user["content"] == [{"type": "text", "text": "hello"}]

    user_with_ctx = _serialize_history_message(
        HumanMessage(
            content="hello",
            additional_kwargs={
                "octop_composer_context": {
                    "skills": ["docx"],
                    "model": "openai/gpt-4o",
                },
            },
        )
    )
    assert user_with_ctx is not None
    assert user_with_ctx.get("composer_context") == {
        "skills": ["docx"],
        "model": "openai/gpt-4o",
    }

    thinking_ai = _serialize_history_message(
        AIMessage(
            content=[
                {"type": "thinking", "thinking": "plan"},
                {"type": "text", "text": "hi"},
            ]
        )
    )
    assert thinking_ai is not None
    assert thinking_ai["content"][0] == {"type": "thinking", "thinking": "plan"}

    tool_call_ai = _serialize_history_message(
        AIMessage(
            content="",
            tool_calls=[
                {"name": "search", "args": {"q": "x"}, "id": "call_1", "type": "tool_call"},
            ],
        )
    )
    assert tool_call_ai is not None
    assert tool_call_ai["content"][0]["type"] == "tool_use"
    assert tool_call_ai["content"][0]["name"] == "search"

    tool_result = _serialize_history_message(
        ToolMessage(content="found", tool_call_id="call_1", name="search")
    )
    assert tool_result is not None
    assert tool_result["role"] == "tool"
    assert tool_result["content"][0]["type"] == "tool_result"
    assert tool_result["content"][0]["output"] == "found"


def test_split_string_thinking_parses_redacted_block() -> None:
    from octop.api.routers.chat.serialize import _split_string_thinking

    blocks = _split_string_thinking("<think>internal</think>Visible answer")
    assert blocks[0] == {"type": "thinking", "thinking": "internal"}
    assert blocks[1] == {"type": "text", "text": "Visible answer"}


def test_serialize_history_message_splits_redacted_thinking() -> None:
    ai = _serialize_history_message(AIMessage(content="<think>internal</think>Visible"))
    assert ai is not None
    assert ai["content"][0] == {"type": "thinking", "thinking": "internal"}
    assert ai["content"][1] == {"type": "text", "text": "Visible"}


def test_strip_thinking_removes_redacted_block() -> None:
    raw = "<think>internal</think>\nPolished prompt"
    assert _strip_thinking(raw) == "Polished prompt"


def test_llm_text_content_strips_thinking_from_string_message() -> None:
    class Msg:
        content = "<think>plan</think>Final text"

    assert _llm_text_content(Msg()) == "Final text"


def test_llm_text_content_skips_thinking_blocks() -> None:
    class Msg:
        content = [
            {"type": "thinking", "thinking": "hidden"},
            {"type": "text", "text": "Visible prompt"},
        ]

    assert _llm_text_content(Msg()) == "Visible prompt"


def test_merge_adjacent_messages_keeps_user_turns_separate() -> None:
    prompt = "每日星座提醒"
    merged = _merge_adjacent_messages(
        [
            {"role": "user", "content": prompt},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "reply one"},
            {"role": "assistant", "content": "reply two"},
        ]
    )
    assert len(merged) == 3
    assert merged[0]["role"] == "user" and merged[0]["content"] == prompt
    assert merged[1]["role"] == "user" and merged[1]["content"] == prompt
    assert merged[2]["role"] == "assistant"
    assert "reply one" in merged[2]["content"]
    assert "reply two" in merged[2]["content"]


def test_entry_matches_thread_by_thread_id() -> None:
    assert _entry_matches_thread(
        {"thread_id": "thr_a", "role": "user", "content": "x"},
        thread_id="thr_a",
        created_at=0,
        last_active=0,
    )
    assert not _entry_matches_thread(
        {"thread_id": "thr_b", "role": "user", "content": "x"},
        thread_id="thr_a",
        created_at=0,
        last_active=0,
    )


def test_entry_matches_thread_does_not_match_by_prompt_title() -> None:
    prompt = "用户星座：双子座。请根据双子座今日运势"
    assert not _entry_matches_thread(
        {"role": "user", "content": prompt},
        thread_id="thr_new",
        created_at=1_000_000,
        last_active=1_000_100,
    )


def test_serialize_history_message_includes_checkpoint_timestamp() -> None:
    user = _serialize_history_message(
        HumanMessage(
            content="hello",
            additional_kwargs={"checkpoint_ts": 1_700_000_000_000},
        )
    )
    assert user is not None
    assert user["timestamp"] == 1_700_000_000_000


def test_serialize_history_message_includes_checkpoint_timestamp_for_tool() -> None:
    tool = _serialize_history_message(
        ToolMessage(
            content="found",
            tool_call_id="call_1",
            name="search",
            additional_kwargs={"checkpoint_ts": 1_700_000_000_123},
        )
    )
    assert tool is not None
    assert tool["timestamp"] == 1_700_000_000_123


def test_ts_to_ms_converts_seconds() -> None:
    assert _ts_to_ms(1_700_000_000.5) == 1_700_000_000_500


@pytest.mark.asyncio
async def test_load_checkpoint_messages_falls_back_to_graph_state() -> None:
    from octop.api.routers.chat.serialize import _load_checkpoint_messages

    human = HumanMessage(content="fallback hello")

    class Harness:
        async def aget_history(self, thread_id: str, *, limit: int = 50) -> list[Any]:
            return []

        graph = MagicMock()
        graph.aget_state = AsyncMock(
            return_value=MagicMock(values={"messages": [human]}),
        )

    msgs, _has_more = await _load_checkpoint_messages(Harness(), "thr_x", limit=10)
    assert len(msgs) == 1
    assert msgs[0].content == "fallback hello"
