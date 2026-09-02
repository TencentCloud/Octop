"""Pure metrics aggregation from trajectory events."""

from __future__ import annotations

from octop.infra.trajectory.metrics import TrajectoryMetrics, aggregate_metrics
from octop.infra.trajectory.types import TrajectoryEvent


def _event(
    *,
    seq: int,
    kind: str,
    payload: dict | None = None,
) -> TrajectoryEvent:
    return TrajectoryEvent(
        event_id=f"T1:{seq}:{kind}",
        thread_id="T1",
        agent_id="A1",
        seq=seq,
        ts=float(seq),
        kind=kind,  # type: ignore[arg-type]
        turn_id=None,
        request_seq=None,
        is_error=False,
        summary="",
        payload=payload or {},
    )


def test_aggregate_metrics_sums_durations_and_tokens() -> None:
    events = [
        _event(
            seq=1,
            kind="assistant",
            payload={
                "llm_duration_ms": 1000.0,
                "ttft_ms": 100.0,
                "tok_per_s": 50.0,
                "input_tokens": 100,
                "output_tokens": 50,
            },
        ),
        _event(
            seq=2,
            kind="assistant",
            payload={
                "llm_duration_ms": 2000.0,
                "ttft_ms": 300.0,
                "tok_per_s": 75.0,
                "input_tokens": 300,
                "output_tokens": 150,
                "cache_read_tokens": 100,
            },
        ),
        _event(seq=3, kind="tool", payload={"tool_duration_ms": 500.0}),
        _event(seq=4, kind="tool", payload={"tool_duration_ms": 300.0}),
        _event(seq=5, kind="tool", payload={"tool_duration_ms": 200.0}),
    ]

    metrics = aggregate_metrics(events)

    assert metrics == TrajectoryMetrics(
        turns=0,
        steps=5,
        llm_duration_ms=3000.0,
        tool_duration_ms=1000.0,
        ttft_avg_ms=200.0,
        tok_per_s=62.5,
        cache_hit_ratio=0.2,
        input_tokens=400,
        output_tokens=200,
        cache_read_tokens=100,
    )


def test_aggregate_metrics_counts_user_turns() -> None:
    events = [
        _event(seq=1, kind="user"),
        _event(seq=2, kind="assistant", payload={"llm_duration_ms": 500.0}),
        _event(seq=3, kind="user"),
    ]

    metrics = aggregate_metrics(events)

    assert metrics.turns == 2
    assert metrics.steps == 3
    assert metrics.llm_duration_ms == 500.0
    assert metrics.tool_duration_ms is None
    assert metrics.ttft_avg_ms is None
    assert metrics.tok_per_s is None
    assert metrics.cache_hit_ratio is None
    assert metrics.input_tokens is None
    assert metrics.output_tokens is None
    assert metrics.cache_read_tokens is None
