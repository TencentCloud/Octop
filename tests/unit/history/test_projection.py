from __future__ import annotations

import asyncio
import json

import pytest
from langchain_core.messages import HumanMessage

from octop.infra.gateway.history_backfill import HistoryBackfillQueue
from octop.infra.gateway.process.message_keys import (
    CHECKPOINT_TS_KEY,
    STREAM_ERROR_FLAG,
    parse_checkpoint_ts_ms,
)
from octop.infra.history.projection import (
    TurnHistoryTracker,
    _wire_text,
    live_message_input,
    message_input,
)


def test_message_input_preserves_existing_checkpoint_ts() -> None:
    item = message_input(
        HumanMessage(
            content="hi",
            additional_kwargs={CHECKPOINT_TS_KEY: 1_700_000_000_000},
        )
    )
    assert item is not None
    wire = json.loads(item.message_json)
    assert wire["data"]["additional_kwargs"][CHECKPOINT_TS_KEY] == 1_700_000_000_000
    assert item.created_at == 1_700_000_000


def test_message_input_does_not_invent_stamp_by_default() -> None:
    item = message_input(HumanMessage(content="hi"))
    assert item is not None
    wire = json.loads(item.message_json)
    assert CHECKPOINT_TS_KEY not in (wire["data"].get("additional_kwargs") or {})


def test_live_message_input_stamps_when_missing() -> None:
    item = live_message_input(
        HumanMessage(content="hi"),
        now_ms=1_700_000_000_123,
    )
    assert item is not None
    wire = json.loads(item.message_json)
    assert wire["data"]["additional_kwargs"][CHECKPOINT_TS_KEY] == 1_700_000_000_123
    assert item.created_at == 1_700_000_000


def test_live_message_input_preserves_existing_stamp() -> None:
    item = live_message_input(
        HumanMessage(
            content="hi",
            additional_kwargs={CHECKPOINT_TS_KEY: 1_700_000_000_000},
        ),
        now_ms=9,
    )
    assert item is not None
    wire = json.loads(item.message_json)
    assert wire["data"]["additional_kwargs"][CHECKPOINT_TS_KEY] == 1_700_000_000_000


def test_parse_checkpoint_ts_ms() -> None:
    assert parse_checkpoint_ts_ms(1_700_000_000) == 1_700_000_000_000
    assert parse_checkpoint_ts_ms(1_700_000_000_000) == 1_700_000_000_000
    assert parse_checkpoint_ts_ms(0) is None
    assert parse_checkpoint_ts_ms(True) is None
    assert parse_checkpoint_ts_ms(None) is None


def test_stream_tokens_stamp_checkpoint_ts() -> None:
    tracker = TurnHistoryTracker.from_request(
        {"messages": [{"role": "user", "content": "hi", "id": "u1"}]}
    )
    tracker.observe({"type": "token", "content": "hello"})
    assistant = next(item for item in tracker.inputs if item.role in ("ai", "assistant"))
    wire = json.loads(assistant.message_json)
    assert CHECKPOINT_TS_KEY in (wire["data"].get("additional_kwargs") or {})


def test_turn_tracker_keeps_only_latest_user_turn_and_dedupes_replay() -> None:
    tracker = TurnHistoryTracker.from_request(
        {"messages": [{"role": "user", "content": "latest", "id": "u2"}]}
    )
    state = [
        {"role": "user", "content": "old", "id": "u1"},
        {"role": "assistant", "content": "old answer", "id": "a1"},
        {"role": "user", "content": "latest", "id": "u2"},
        {"role": "assistant", "content": "new answer", "id": "a2"},
    ]
    tracker.observe({"type": "state_snapshot", "data": {"messages": state}})
    tracker.observe({"type": "state_update", "data": {"messages": state}})

    assert [item.message_id for item in tracker.inputs] == ["u2", "a2"]


def test_turn_tracker_keeps_streamed_tokens_and_error() -> None:
    tracker = TurnHistoryTracker.from_request(
        {"messages": [{"role": "user", "content": "continue this", "id": "u1"}]}
    )
    tracker.observe({"type": "token", "content": "partial "})
    tracker.observe({"type": "token", "content": "answer"})
    tracker.observe(
        {
            "type": "error",
            "message": "模型服务返回余额或额度不足。",
            "error_code": "TOKEN_QUOTA_EXCEEDED",
        }
    )

    texts = [_wire_text(item) for item in tracker.inputs]
    assert any("continue this" in text for text in texts)
    assert "partial answer" in texts
    assert any("余额或额度不足" in text for text in texts)
    error = next(item for item in tracker.inputs if "余额或额度不足" in _wire_text(item))
    assert STREAM_ERROR_FLAG in error.message_json


def test_turn_tracker_does_not_duplicate_state_assistant() -> None:
    tracker = TurnHistoryTracker.from_request(
        {"messages": [{"role": "user", "content": "hi", "id": "u1"}]}
    )
    tracker.observe({"type": "token", "content": "hello"})
    tracker.observe(
        {
            "type": "state_snapshot",
            "data": {
                "messages": [
                    {"role": "user", "content": "hi", "id": "u1"},
                    {"role": "assistant", "content": "hello world", "id": "a1"},
                ]
            },
        }
    )

    texts = [_wire_text(item) for item in tracker.inputs]
    assert texts.count("hello") == 0
    assert any(text == "hello world" for text in texts)


@pytest.mark.asyncio
async def test_backfill_queue_runs_one_job_at_a_time_and_dedupes() -> None:
    queue = HistoryBackfillQueue(max_pending=2)
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    order: list[str] = []

    async def first() -> None:
        order.append("first:start")
        first_started.set()
        await release_first.wait()
        order.append("first:end")

    async def second() -> None:
        order.append("second")

    assert queue.enqueue("thr-1", first) is True
    assert queue.enqueue("thr-1", first) is True
    assert queue.enqueue("thr-2", second) is True
    assert queue.available_slots == 0
    assert queue.active_jobs == 2
    assert queue.contains("thr-1") is True
    await first_started.wait()
    assert order == ["first:start"]
    assert queue.available_slots == 1
    release_first.set()
    await asyncio.wait_for(queue._queue.join(), timeout=1)  # noqa: SLF001
    assert order == ["first:start", "first:end", "second"]
    assert queue.active_jobs == 0
    assert queue.available_slots == 2
    assert queue.contains("thr-1") is False
    await queue.close()


def _tool_turn(*, identical: bool = False):
    from langchain_core.messages import AIMessage, ToolMessage

    human = HumanMessage(content="question", id="u1")
    first = AIMessage(
        content="same" if identical else "before tool",
        id="a1",
        tool_calls=[{"id": "call1", "name": "lookup", "args": {}}],
    )
    result = ToolMessage(content="result", id="t1", tool_call_id="call1")
    last = AIMessage(content="same" if identical else "after tool", id="a2")
    return human, first, result, last


@pytest.mark.parametrize("identified", [True, False])
@pytest.mark.parametrize("identical", [True, False])
def test_turn_tracker_keeps_tool_answers_without_aggregate_duplicate(identified, identical):
    human, first, tool, last = _tool_turn(identical=identical)
    tracker = TurnHistoryTracker(seed_messages=[human])
    for message in (first, last):
        chunk = {"type": "token", "content": message.content}
        if identified:
            chunk["message_id"] = message.id
        tracker.observe(chunk)
        if message is first:
            tracker.observe({"type": "tool_result", "messages": [tool]})
    snapshot = {"type": "state_snapshot", "data": {"messages": [human, first, tool, last]}}
    tracker.observe(snapshot)
    tracker.observe(snapshot)
    assert [item.message_id for item in tracker.inputs] == ["u1", "a1", "t1", "a2"]


@pytest.mark.parametrize("identified", [True, False])
def test_turn_tracker_retains_only_uncovered_partial_answer(identified):
    human, first, tool, _ = _tool_turn()
    tracker = TurnHistoryTracker(seed_messages=[human])
    tracker.observe(
        {"type": "token", "content": "before tool", **({"message_id": "a1"} if identified else {})}
    )
    tracker.observe({"type": "tool_result", "messages": [tool]})
    tracker.observe(
        {
            "type": "token",
            "content": "partial after",
            **({"message_id": "a2"} if identified else {}),
        }
    )
    tracker.observe({"type": "state_snapshot", "data": {"messages": [human, first, tool]}})
    assert [_wire_text(item) for item in tracker.inputs] == [
        "question",
        "before tool",
        "result",
        "partial after",
    ]


def test_turn_tracker_does_not_drop_same_text_from_a_different_message():
    from langchain_core.messages import AIMessage

    tracker = TurnHistoryTracker(seed_messages=[HumanMessage(content="question", id="u1")])
    tracker.observe({"type": "token", "content": "same", "message_id": "a1"})
    tracker.observe({"type": "tool_result"})
    tracker.observe({"type": "token", "content": "same", "message_id": "a2"})
    tracker.observe(
        {"type": "state_update", "data": {"messages": [AIMessage(content="same", id="a1")]}}
    )
    assert [item.message_id for item in tracker.inputs] == ["u1", "a1", "a2"]
    assert [_wire_text(item) for item in tracker.inputs] == ["question", "same", "same"]


def test_turn_tracker_keeps_reasoning_with_its_assistant():
    human, first, tool, last = _tool_turn()
    tracker = TurnHistoryTracker(seed_messages=[human])
    tracker.observe({"type": "reasoning", "content": "first thought", "message_id": "a1"})
    tracker.observe({"type": "token", "content": "before tool", "message_id": "a1"})
    tracker.observe({"type": "tool_result", "messages": [tool]})
    tracker.observe({"type": "reasoning", "content": "second thought", "message_id": "a2"})
    tracker.observe({"type": "token", "content": "after tool", "message_id": "a2"})
    tracker.observe({"type": "state_snapshot", "data": {"messages": [human, first, tool, last]}})
    assistants = [
        json.loads(item.message_json)["data"] for item in tracker.inputs if item.role == "ai"
    ]
    assert [a["additional_kwargs"]["reasoning_content"] for a in assistants] == [
        "first thought",
        "second thought",
    ]
    assert [a["content"] for a in assistants] == ["before tool", "after tool"]


def test_turn_tracker_extends_partial_state_without_losing_tool_calls():
    from langchain_core.messages import AIMessage

    tracker = TurnHistoryTracker()
    tracker.observe({"type": "token", "content": "complete answer", "message_id": "a1"})
    tracker.observe(
        {
            "type": "state_update",
            "data": {
                "messages": [
                    AIMessage(
                        content="complete",
                        id="a1",
                        tool_calls=[{"id": "call", "name": "lookup", "args": {}}],
                    )
                ]
            },
        }
    )
    assert len(tracker.inputs) == 1
    data = json.loads(tracker.inputs[0].message_json)["data"]
    assert data["content"] == "complete answer"
    assert data["tool_calls"][0]["id"] == "call"


def test_turn_tracker_preserves_structured_state_and_streamed_suffix():
    from langchain_core.messages import AIMessage

    tracker = TurnHistoryTracker()
    tracker.observe({"type": "token", "message_id": "a1", "content": "hello world"})
    tracker.observe(
        {
            "type": "state_update",
            "data": {
                "messages": [
                    AIMessage(
                        id="a1",
                        content=[
                            {"type": "text", "text": "hello"},
                            {"type": "image_url", "image_url": {"url": "test-image"}},
                        ],
                    )
                ]
            },
        }
    )
    assert len(tracker.inputs) == 1
    data = json.loads(tracker.inputs[0].message_json)["data"]
    assert data["content"][1] == {"type": "image_url", "image_url": {"url": "test-image"}}
    assert _wire_text(tracker.inputs[0]) == "hello world"


def test_turn_tracker_retains_reasoning_only_interruption():
    tracker = TurnHistoryTracker()
    tracker.observe({"type": "reasoning", "message_id": "a1", "content": "thinking"})
    assert len(tracker.inputs) == 1
    data = json.loads(tracker.inputs[0].message_json)["data"]
    assert data["id"] == "a1"
    assert data["content"] == ""
    assert data["additional_kwargs"]["reasoning_content"] == "thinking"


def test_turn_tracker_splits_unidentified_sources():
    tracker = TurnHistoryTracker()
    tracker.observe({"type": "token", "node": "first", "content": "first answer"})
    tracker.observe({"type": "token", "node": "second", "content": "second answer"})
    assert [_wire_text(item) for item in tracker.inputs] == ["first answer", "second answer"]


@pytest.mark.parametrize(
    ("streamed", "saved"),
    [("answer", "other answer"), ("answer", "answer extended"), ("answer extended", "answer")],
)
def test_turn_tracker_does_not_match_unidentified_partial_text(streamed, saved):
    from langchain_core.messages import AIMessage

    tracker = TurnHistoryTracker()
    tracker.observe({"type": "token", "content": streamed})
    tracker.observe({"type": "reasoning", "content": "unidentified thought"})
    tracker.observe(
        {
            "type": "state_update",
            "data": {"messages": [AIMessage(content=saved), AIMessage(content="another reply")]},
        }
    )

    assert [_wire_text(item) for item in tracker.inputs] == [saved, "another reply", streamed]
    data = [json.loads(item.message_json)["data"] for item in tracker.inputs]
    assert "reasoning_content" not in data[0]["additional_kwargs"]
    assert "reasoning_content" not in data[1]["additional_kwargs"]
    assert data[2]["additional_kwargs"]["reasoning_content"] == "unidentified thought"


@pytest.mark.parametrize(
    ("streamed", "saved"), [("answer", "other answer"), ("answer extended", "answer")]
)
def test_turn_tracker_does_not_rewrite_unidentified_single_answer(streamed, saved):
    from langchain_core.messages import AIMessage

    tracker = TurnHistoryTracker()
    tracker.observe({"type": "token", "content": streamed})
    tracker.observe({"type": "state_update", "data": {"messages": [AIMessage(content=saved)]}})
    assert [_wire_text(item) for item in tracker.inputs] == [saved, streamed]
