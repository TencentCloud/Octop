"""Tests for Octop context-usage adapter over harness-agent."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.agents.context_breakdown import (
    SEGMENT_KEYS,
    compute_context_breakdown,
)


def test_segment_keys_stable() -> None:
    assert "conversation" in SEGMENT_KEYS
    assert "system_prompt" in SEGMENT_KEYS
    assert "skills" in SEGMENT_KEYS


def test_segment_keys_match_harness_when_available() -> None:
    pytest.importorskip("harness_agent.context_usage")
    from harness_agent.context_usage import SEGMENT_KEYS as HARNESS_KEYS

    assert SEGMENT_KEYS == HARNESS_KEYS


def _usage(
    *,
    used: int,
    segments: dict[str, int],
    source: str = "model_request",
    max_tokens: int = 128_000,
) -> SimpleNamespace:
    obj = SimpleNamespace(
        max_tokens=max_tokens,
        used_tokens=used,
        input_tokens=used,
        output_tokens=0,
        segments=segments,
        source=source,
    )

    def with_max_tokens(cap: int) -> SimpleNamespace:
        return SimpleNamespace(
            max_tokens=cap,
            used_tokens=obj.used_tokens,
            input_tokens=obj.input_tokens,
            output_tokens=obj.output_tokens,
            segments=dict(obj.segments),
            source=obj.source,
            with_max_tokens=with_max_tokens,
        )

    obj.with_max_tokens = with_max_tokens  # type: ignore[attr-defined]
    return obj


def _registry(usage: object | None) -> MagicMock:
    registry = MagicMock()
    registry.get_row.return_value = MagicMock()
    harness = MagicMock()
    # None → older harness without aget_context_usage
    harness.aget_context_usage = None if usage is None else AsyncMock(return_value=usage)
    registry.get_agent.return_value = harness
    return registry


@pytest.mark.asyncio
async def test_prefers_harness_snapshot() -> None:
    usage = _usage(
        used=9_000,
        segments={
            "system_prompt": 1_000,
            "skills": 2_000,
            "tool_definitions": 1_500,
            "conversation": 4_500,
        },
    )
    result = await compute_context_breakdown(
        _registry(usage),
        agent_id="agt",
        thread_id="t1",
        max_tokens=100_000,
        input_tokens=9999,
    )
    assert result.max_tokens == 100_000
    assert result.used_tokens == 9_000
    assert result.segments["skills"] == 2_000
    assert result.segments["conversation"] == 4_500


@pytest.mark.asyncio
async def test_fallback_to_stream_input_tokens_when_empty() -> None:
    empty = _usage(used=0, segments={}, source="empty")
    result = await compute_context_breakdown(
        _registry(empty),
        agent_id="agt",
        thread_id="t1",
        max_tokens=128_000,
        input_tokens=9_000,
    )
    assert result.used_tokens == 9_000
    assert result.segments["conversation"] == 9_000
    assert result.segments["skills"] == 0
    assert result.segments["system_prompt"] == 0


@pytest.mark.asyncio
async def test_fallback_when_harness_lacks_getter() -> None:
    result = await compute_context_breakdown(
        _registry(None),
        agent_id="agt",
        thread_id="t1",
        max_tokens=128_000,
        input_tokens=4_200,
    )
    assert result.used_tokens == 4_200
    assert result.segments["conversation"] == 4_200


@pytest.mark.asyncio
async def test_missing_agent() -> None:
    registry = MagicMock()
    registry.get_row.return_value = None
    with pytest.raises(ValueError, match="not found"):
        await compute_context_breakdown(
            registry,
            agent_id="missing",
            thread_id="t",
            max_tokens=128_000,
        )


@pytest.mark.asyncio
async def test_empty_without_stream_tokens() -> None:
    empty = _usage(used=0, segments={}, source="empty")
    result = await compute_context_breakdown(
        _registry(empty),
        agent_id="agt",
        thread_id="t1",
        max_tokens=64_000,
    )
    assert result.used_tokens == 0
    assert all(v == 0 for v in result.segments.values())
