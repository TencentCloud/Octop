"""Aggregate session metrics from trajectory events."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from octop.infra.trajectory.types import TrajectoryEvent


@dataclass(frozen=True)
class TrajectoryMetrics:
    turns: int
    steps: int
    llm_duration_ms: float | None
    tool_duration_ms: float | None
    ttft_avg_ms: float | None
    tok_per_s: float | None
    cache_hit_ratio: float | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _int_value(value: object) -> int | None:
    number = _numeric(value)
    if number is None:
        return None
    return int(number)


def _sum_payload(events: Sequence[TrajectoryEvent], key: str) -> float | None:
    total = 0.0
    found = False
    for event in events:
        value = _numeric(event.payload.get(key))
        if value is None:
            continue
        total += value
        found = True
    return total if found else None


def _sum_payload_int(events: Sequence[TrajectoryEvent], key: str) -> int | None:
    total = 0
    found = False
    for event in events:
        value = _int_value(event.payload.get(key))
        if value is None:
            continue
        total += value
        found = True
    return total if found else None


def _avg_payload(events: Sequence[TrajectoryEvent], key: str) -> float | None:
    values: list[float] = []
    for event in events:
        value = _numeric(event.payload.get(key))
        if value is not None:
            values.append(value)
    if not values:
        return None
    return sum(values) / len(values)


def aggregate_metrics(events: Sequence[TrajectoryEvent]) -> TrajectoryMetrics:
    """Roll up session metrics from trajectory events.

    ``turns`` counts events with ``kind == "user"`` (not distinct ``turn_id``).
    ``steps`` is ``len(events)``. Duration and token fields sum across events
    that carry them; ``ttft_avg_ms`` and ``tok_per_s`` average assistant payloads.
    ``cache_hit_ratio`` is ``cache_read / (input + cache_read)`` when both sums
    exist. Missing numeric inputs stay ``None``.
    """
    assistant_events = [event for event in events if event.kind == "assistant"]
    tool_events = [event for event in events if event.kind == "tool"]

    input_tokens = _sum_payload_int(events, "input_tokens")
    output_tokens = _sum_payload_int(events, "output_tokens")
    cache_read_tokens = _sum_payload_int(events, "cache_read_tokens")

    cache_hit_ratio: float | None = None
    if input_tokens is not None and cache_read_tokens is not None:
        denom = input_tokens + cache_read_tokens
        if denom > 0:
            cache_hit_ratio = cache_read_tokens / denom

    return TrajectoryMetrics(
        turns=sum(1 for event in events if event.kind == "user"),
        steps=len(events),
        llm_duration_ms=_sum_payload(assistant_events, "llm_duration_ms"),
        tool_duration_ms=_sum_payload(tool_events, "tool_duration_ms"),
        ttft_avg_ms=_avg_payload(assistant_events, "ttft_ms"),
        tok_per_s=_avg_payload(assistant_events, "tok_per_s"),
        cache_hit_ratio=cache_hit_ratio,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
    )
