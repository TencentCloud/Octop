"""Turn-level token usage extraction (multi-call agent loops)."""

from __future__ import annotations

from types import SimpleNamespace

from octop.infra.gateway.process.usage_record import (
    UsageTracker,
    extract_usage_from_chunk,
    turn_usage_from_messages,
)


def _ai(
    input_tokens: int,
    output_tokens: int,
    *,
    model: str = "openai:gpt-4o-mini",
) -> dict[str, object]:
    return {
        "role": "assistant",
        "content": "ok",
        "usage_metadata": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
        "response_metadata": {"model_name": model},
    }


def test_turn_usage_sums_all_ai_calls_after_last_user() -> None:
    messages = [
        {"role": "user", "content": "first"},
        _ai(10, 2),
        {"role": "user", "content": "second"},
        _ai(100, 20),
        {"role": "tool", "content": "result"},
        _ai(200, 30, model="openai:gpt-4o"),
    ]
    out = turn_usage_from_messages(messages)
    assert out is not None
    assert out["input_tokens"] == 300
    assert out["output_tokens"] == 50
    assert out["total_tokens"] == 350
    assert out["model"] == "openai:gpt-4o"


def test_turn_usage_from_langchain_style_objects() -> None:
    messages = [
        SimpleNamespace(type="human", content="hi"),
        SimpleNamespace(
            type="ai",
            usage_metadata={"input_tokens": 7, "output_tokens": 3},
            response_metadata={"model": "m1"},
        ),
        SimpleNamespace(
            type="ai",
            usage_metadata={"prompt_tokens": 8, "completion_tokens": 4},
            response_metadata={"model_name": "m2"},
        ),
    ]
    out = turn_usage_from_messages(messages)
    assert out == {
        "input_tokens": 15,
        "uncached_input_tokens": 15,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 7,
        "reasoning_tokens": 0,
        "total_tokens": 22,
        "model": "m2",
        "model_calls": 2,
        "last_input_tokens": 8,
    }


def test_turn_usage_skips_malformed_token_fields() -> None:
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "usage_metadata": {"input_tokens": {"cache": 9}, "output_tokens": "nope"},
        },
        _ai(12, 3),
    ]
    out = turn_usage_from_messages(messages)
    assert out is not None
    assert out["input_tokens"] == 12
    assert out["output_tokens"] == 3


def test_extract_snapshot_sums_current_turn_not_last_call() -> None:
    chunk = {
        "type": "state_snapshot",
        "data": {
            "messages": [
                {"role": "user", "content": "hi"},
                _ai(1_000, 50),
                _ai(20_000, 80),
            ],
        },
    }
    out = extract_usage_from_chunk(chunk)
    assert out is not None
    assert out["input_tokens"] == 21_000
    assert out["output_tokens"] == 130


def test_tracker_snapshot_is_authoritative_over_later_updates() -> None:
    tracker = UsageTracker()
    tracker.observe(
        {
            "type": "state_snapshot",
            "data": {
                "messages": [
                    {"role": "user", "content": "hi"},
                    _ai(100, 10),
                ],
            },
        }
    )
    # Same (or extra) AI replayed as an incremental update must not add.
    tracker.observe({"type": "state_update", "data": {"messages": [_ai(100, 10)]}})
    tracker.observe({"type": "state_update", "data": {"messages": [_ai(200, 20)]}})
    assert tracker.usage is not None
    assert tracker.usage["input_tokens"] == 100
    assert tracker.usage["output_tokens"] == 10

    tracker.observe(
        {
            "type": "state_snapshot",
            "data": {
                "messages": [
                    {"role": "user", "content": "hi"},
                    _ai(100, 10),
                    _ai(200, 20),
                ],
            },
        }
    )
    assert tracker.usage["input_tokens"] == 300
    assert tracker.usage["output_tokens"] == 30


def test_tracker_updates_accumulate_until_first_snapshot() -> None:
    tracker = UsageTracker()
    tracker.observe({"type": "state_update", "data": {"messages": [_ai(10, 1)]}})
    tracker.observe({"type": "state_update", "data": {"messages": [_ai(20, 2)]}})
    assert tracker.usage is not None
    assert tracker.usage["input_tokens"] == 30
    assert tracker.usage["output_tokens"] == 3

    tracker.observe(
        {
            "type": "state_snapshot",
            "data": {
                "messages": [
                    {"role": "user", "content": "hi"},
                    _ai(10, 1),
                    _ai(20, 2),
                ],
            },
        }
    )
    assert tracker.usage["input_tokens"] == 30
    assert tracker.usage["output_tokens"] == 3


def test_tracker_history_shaped_update_does_not_double_count() -> None:
    tracker = UsageTracker()
    messages = [
        {"role": "user", "content": "hi"},
        _ai(100, 10),
        _ai(200, 20),
    ]
    tracker.observe({"type": "state_snapshot", "data": {"messages": messages}})
    tracker.observe({"type": "state_update", "data": {"messages": messages}})
    assert tracker.usage is not None
    assert tracker.usage["input_tokens"] == 300
    assert tracker.usage["output_tokens"] == 30
