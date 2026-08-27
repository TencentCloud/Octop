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


def _registry(usage: object | None, *, history: list[object] | None = None) -> MagicMock:
    registry = MagicMock()
    registry.get_row.return_value = MagicMock()
    harness = MagicMock()
    harness._context_usage_mw = (
        None if usage is None else SimpleNamespace(get_snapshot=MagicMock(return_value=usage))
    )
    harness.aget_context_usage = AsyncMock(side_effect=AssertionError("must not read checkpoint"))
    harness.aget_history = AsyncMock(return_value=list(history or []))
    registry.get_agent.return_value = harness
    return registry


@pytest.mark.asyncio
async def test_prefers_harness_snapshot() -> None:
    usage = _usage(
        used=9_000,
        max_tokens=1_000_000,
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
    assert result.max_tokens == 1_000_000
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


@pytest.mark.asyncio
async def test_does_not_recover_response_metadata_from_checkpoint() -> None:
    empty = _usage(used=0, segments={}, source="empty")
    history = [
        {
            "role": "assistant",
            "content": "ok",
            "response_metadata": {"token_usage": {"prompt_tokens": 8800, "completion_tokens": 40}},
        },
    ]
    result = await compute_context_breakdown(
        _registry(empty, history=history),
        agent_id="agt",
        thread_id="t1",
        max_tokens=128_000,
    )
    assert result.used_tokens == 0


@pytest.mark.asyncio
async def test_does_not_read_checkpoint_context_stamp() -> None:
    empty = _usage(used=0, segments={}, source="empty")
    history = [
        {
            "role": "assistant",
            "content": "ok",
            "additional_kwargs": {
                "context_usage": {
                    "max_tokens": 128_000,
                    "used_tokens": 15_400,
                    "input_tokens": 15_400,
                    "output_tokens": 80,
                    "segments": {
                        "system_prompt": 2_000,
                        "conversation": 13_400,
                    },
                }
            },
        },
    ]
    result = await compute_context_breakdown(
        _registry(empty, history=history),
        agent_id="agt",
        thread_id="t1",
        max_tokens=1_000_000,
    )
    assert result.max_tokens == 1_000_000
    assert result.used_tokens == 0


@pytest.mark.asyncio
async def test_empty_snapshot_uses_usage_ledger_without_checkpoint() -> None:
    empty = _usage(used=0, segments={}, source="empty")
    history = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "ok",
            "usage_metadata": {"input_tokens": 4200, "output_tokens": 12},
        },
    ]
    registry = _registry(empty, history=history)
    usage_repo = MagicMock()
    usage_repo.last_thread_input_tokens.return_value = 4200
    result = await compute_context_breakdown(
        registry,
        agent_id="agt",
        thread_id="t1",
        max_tokens=128_000,
        usage_repo=usage_repo,
    )
    assert result.used_tokens == 4200
    assert result.segments["conversation"] == 4200
    registry.get_agent.return_value.aget_history.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_harness_missing_falls_back_to_query_hint() -> None:
    registry = MagicMock()
    registry.get_row.return_value = MagicMock()
    registry.get_agent.side_effect = RuntimeError("agent not running")
    result = await compute_context_breakdown(
        registry,
        agent_id="agt",
        thread_id="t1",
        max_tokens=128_000,
        input_tokens=9_000,
    )
    assert result.used_tokens == 9_000
    assert result.segments["conversation"] == 9_000
