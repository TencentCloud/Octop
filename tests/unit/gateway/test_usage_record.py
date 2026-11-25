"""Turn-level token usage extraction (multi-call agent loops)."""

from __future__ import annotations

from types import SimpleNamespace

from tests.support.otel import active_telemetry, metric_points

from octop.infra.gateway.process.usage_record import (
    UsageTracker,
    extract_usage_from_chunk,
    record_turn_usage,
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


class _UsageRepo:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.rows: list[dict[str, object]] = []

    def record(self, **kwargs: object) -> int:
        if self.fail:
            raise RuntimeError("db down")
        self.rows.append(kwargs)
        return len(self.rows)


def test_record_turn_usage_emits_telemetry() -> None:
    repo = _UsageRepo()
    with active_telemetry() as reader:
        record_turn_usage(
            repo,
            agent_id="a1",
            user_id=1,
            thread_id="t1",
            usage={
                "input_tokens": 120,
                "cache_read_tokens": 20,
                "output_tokens": 30,
                "model": "m1",
            },
            source="cron",
        )
        (inp,) = metric_points(reader, "gen_ai.client.inference.usage.input_tokens")
        (out,) = metric_points(reader, "gen_ai.client.inference.usage.output_tokens")
        (cache,) = metric_points(reader, "gen_ai.client.inference.usage.cache_read.input_tokens")
    assert len(repo.rows) == 1
    assert (inp.value, out.value, cache.value) == (120, 30, 20)
    assert inp.attributes["octop.usage.source"] == "cron"
    assert inp.attributes["gen_ai.response.model"] == "m1"


def test_record_turn_usage_emits_even_if_db_write_fails() -> None:
    repo = _UsageRepo(fail=True)
    with active_telemetry() as reader:
        record_turn_usage(
            repo,
            agent_id="a1",
            user_id=1,
            thread_id="t1",
            usage={"input_tokens": 9, "output_tokens": 1, "model": "m1"},
        )
        (inp,) = metric_points(reader, "gen_ai.client.inference.usage.input_tokens")
    assert inp.value == 9


def test_tracker_usage_records_one_observation_per_model_call() -> None:
    tracker = UsageTracker(request_model="janus/deepseek-v4.1-flash")
    messages = [
        {"role": "user", "content": "q"},
        {**_ai(100, 10, model="deepseek-v4-1-flash-261017"), "id": "c1"},
        {**_ai(300, 30, model="deepseek-v4-1-flash-261017"), "id": "c2"},
    ]
    tracker.observe({"type": "state_snapshot", "data": {"messages": messages}})
    repo = _UsageRepo()
    with active_telemetry() as reader:
        record_turn_usage(repo, agent_id="a1", user_id=1, thread_id="t1", usage=tracker.usage or {})
        (inp,) = metric_points(reader, "gen_ai.client.inference.usage.input_tokens")
        (op_in,) = metric_points(reader, "gen_ai.client.inference.operation.input_tokens")
    # Counters sum the turn; the histogram sees each call separately.
    assert inp.value == 400
    assert (op_in.count, op_in.sum) == (2, 400)
    assert inp.attributes["gen_ai.request.model"] == "deepseek-v4.1-flash"
    assert inp.attributes["gen_ai.response.model"] == "deepseek-v4-1-flash-261017"
    # The persisted row stays one-per-turn.
    assert len(repo.rows) == 1
    assert repo.rows[0]["model_calls"] == 2


def test_tracker_context_stays_out_of_the_dict_payload() -> None:
    tracker = UsageTracker(request_model="janus/m1")
    tracker.observe({"usage": {"input_tokens": 3, "output_tokens": 1, "model": "m1-001"}})
    usage = tracker.usage
    assert usage is not None
    assert usage.request_model == "janus/m1"
    assert len(usage.calls) == 1
    # Merged into persisted payloads via ``{**payload, **usage}``: must stay clean.
    assert "request_model" not in {**usage}
    assert "calls" not in {**usage}
    assert UsageTracker().usage is None


def test_request_model_ref_splits_provider_from_model_id() -> None:
    repo = _UsageRepo()
    tracker = UsageTracker(request_model="hf/Qwen/Qwen3-8B")
    tracker.observe({"usage": {"input_tokens": 9, "output_tokens": 1}})
    with active_telemetry() as reader:
        record_turn_usage(repo, agent_id="a1", user_id=1, thread_id="t1", usage=tracker.usage or {})
        (inp,) = metric_points(reader, "gen_ai.client.inference.usage.input_tokens")
    assert inp.attributes["gen_ai.request.model"] == "Qwen/Qwen3-8B"
    assert inp.attributes["gen_ai.provider.name"] == "hf"


def test_auto_routed_turn_has_no_request_model_or_provider() -> None:
    repo = _UsageRepo()
    tracker = UsageTracker()
    tracker.observe({"usage": {"input_tokens": 9, "output_tokens": 1, "model": "m1"}})
    with active_telemetry() as reader:
        record_turn_usage(repo, agent_id="a1", user_id=1, thread_id="t1", usage=tracker.usage or {})
        (inp,) = metric_points(reader, "gen_ai.client.inference.usage.input_tokens")
    assert "gen_ai.request.model" not in inp.attributes
    assert "gen_ai.provider.name" not in inp.attributes
