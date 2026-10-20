"""Tests for context-window usage estimation and persistence."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool

from octop_harness.context_usage import (
    CONTEXT_USAGE_KEY,
    ContextUsage,
    breakdown_from_model_request,
    build_context_usage,
    content_tokens,
    context_usage_from_messages,
    conversation_tokens_from_messages,
    estimate_json_tokens,
    estimate_tokens,
    message_content_text,
    scale_segments,
    shrink_context_usage,
    tool_schema_tokens,
)
from octop_harness.middleware.context_usage import ContextUsageMiddleware, resolve_context_usage


def test_estimate_tokens_empty() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1


def test_tool_schema_tokens_caches_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop_harness import context_usage as cu

    monkeypatch.setattr(cu, "_TOOL_SCHEMA_TOKEN_CACHE", {})
    tool = MagicMock()
    tool.name = "read_file"
    calls = {"n": 0}

    def fake_convert(t: Any) -> dict[str, Any]:
        calls["n"] += 1
        return {"type": "function", "function": {"name": t.name, "parameters": {}}}

    monkeypatch.setattr(
        "langchain_core.utils.function_calling.convert_to_openai_tool",
        fake_convert,
    )
    a = tool_schema_tokens(tool)
    b = tool_schema_tokens(tool)
    assert a == b
    assert calls["n"] == 1


def test_deferred_tool_estimate_omits_parameter_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop_harness import context_usage as cu

    monkeypatch.setattr(cu, "_TOOL_SCHEMA_TOKEN_CACHE", {})

    def render(prompt: str, size: int = 1000) -> str:
        return prompt[:size]

    eager = StructuredTool.from_function(render, name="render_media", description="Render media")
    deferred = eager.model_copy(update={"extras": {"defer_loading": True}})

    assert tool_schema_tokens(deferred) < tool_schema_tokens(eager)


def test_partition_system_prompt_segments() -> None:
    from octop_harness.context_usage import partition_system_prompt_segments

    text = (
        "You are helpful.\n\n"
        "<agent_memory>\n# Project rules\nBe careful.\n</agent_memory>\n\n"
        "## Skills System\n**Available Skills:**\n- foo: does foo\n"
    )
    parts = partition_system_prompt_segments(text)
    assert parts["system_prompt"] > 0
    assert parts["rules"] > 0
    assert parts["skills"] > 0


def test_breakdown_from_model_request_buckets_tools() -> None:
    read_tool = MagicMock()
    read_tool.name = "read_file"
    mcp_tool = MagicMock()
    mcp_tool.name = "mcp_server_foo"
    task_tool = MagicMock()
    task_tool.name = "task"

    request = SimpleNamespace(
        system_message=SystemMessage(content="You are helpful." * 20),
        system_prompt=None,
        tools=[read_tool, mcp_tool, task_tool],
        messages=[HumanMessage(content="hello world")],
    )
    raw = breakdown_from_model_request(
        request,
        mcp_tool_names=frozenset({"mcp_server_foo"}),
    )
    assert raw["system_prompt"] > 0
    assert raw["conversation"] > 0
    assert raw["tool_definitions"] > 0
    assert raw["mcp"] > 0
    assert raw["subagent_definitions"] > 0
    assert raw["rules"] == 0
    assert raw["skills"] == 0


def test_scale_segments_matches_target() -> None:
    raw = {
        "system_prompt": 100,
        "tool_definitions": 50,
        "rules": 0,
        "skills": 0,
        "mcp": 25,
        "subagent_definitions": 25,
        "conversation": 800,
    }
    scaled = scale_segments(raw, 1000)
    assert sum(scaled.values()) == 1000
    assert scaled["conversation"] > scaled["system_prompt"]


def test_build_context_usage_keeps_provider_total_and_raw_estimates() -> None:
    request = SimpleNamespace(
        system_message=SystemMessage(content="sys " * 100),
        system_prompt=None,
        tools=[],
        messages=[HumanMessage(content="hi " * 100)],
    )
    ai = AIMessage(
        content="ok",
        usage_metadata={"input_tokens": 500, "output_tokens": 12, "total_tokens": 512},
    )
    usage = build_context_usage(request, response_messages=[ai], max_tokens=128_000)
    assert usage.source == "model_request"
    assert usage.input_tokens == 500
    assert usage.output_tokens == 12
    assert usage.used_tokens == 500
    assert 0 < sum(usage.segments.values()) < 500


def test_build_context_usage_preserves_cache_details() -> None:
    request = SimpleNamespace(
        system_message=SystemMessage(content="system"),
        system_prompt=None,
        tools=[],
        messages=[HumanMessage(content="hi")],
    )
    ai = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": 500,
            "output_tokens": 12,
            "total_tokens": 512,
            "output_token_details": {"reasoning": 4},
        },
        response_metadata={
            "token_usage": {
                "prompt_tokens": 500,
                "completion_tokens": 12,
                "prompt_cache_hit_tokens": 300,
                "input_token_details": {"cache_creation": 50},
            }
        },
    )

    usage = build_context_usage(request, response_messages=[ai])

    assert usage.uncached_input_tokens == 150
    assert usage.cache_read_tokens == 300
    assert usage.cache_write_tokens == 50
    assert usage.reasoning_tokens == 4


def test_context_usage_roundtrip_on_message() -> None:
    usage = ContextUsage(
        max_tokens=1000,
        used_tokens=100,
        input_tokens=100,
        output_tokens=5,
        segments={"system_prompt": 40, "conversation": 60},
        source="model_request",
    )
    ai = AIMessage(
        content="done",
        additional_kwargs={CONTEXT_USAGE_KEY: usage.to_dict()},
    )
    loaded = context_usage_from_messages([HumanMessage(content="q"), ai])
    assert loaded is not None
    assert loaded.used_tokens == 100
    assert loaded.segments["conversation"] == 60


def test_from_dict_keeps_stock_stamp_without_source() -> None:
    loaded = ContextUsage.from_dict(
        {
            "max_tokens": 128_000,
            "used_tokens": 15_400,
            "input_tokens": 15_400,
            "segments": {"conversation": 15_400},
        }
    )
    assert loaded.source == "model_request"
    assert loaded.used_tokens == 15_400


def test_with_max_tokens_restores_uncapped_input() -> None:
    """Raising the cap after a 128k stamp should surface real input_tokens."""
    usage = ContextUsage(
        max_tokens=128_000,
        used_tokens=128_000,
        input_tokens=135_000,
        output_tokens=10,
        segments={"conversation": 128_000},
        source="model_request",
    )
    raised = usage.with_max_tokens(1_000_000)
    assert raised.max_tokens == 1_000_000
    assert raised.used_tokens == 135_000
    assert raised.input_tokens == 135_000


def test_middleware_stamps_response_and_memory() -> None:
    mw = ContextUsageMiddleware(mcp_tool_names=frozenset())
    request = MagicMock()
    request.system_message = SystemMessage(content="You are a bot. " * 30)
    request.system_prompt = None
    request.tools = []
    request.messages = [HumanMessage(content="hello")]
    request.runtime = None

    ai = AIMessage(
        content="world",
        usage_metadata={"input_tokens": 200, "output_tokens": 3, "total_tokens": 203},
    )
    from langchain.agents.middleware import ModelResponse

    response = ModelResponse(result=[ai])

    # Inject thread_id via langgraph config context when available is hard in
    # unit tests — call _capture directly after patching thread lookup.
    stamped = mw._capture(request, response)
    assert isinstance(stamped.result[0], AIMessage)
    payload = stamped.result[0].additional_kwargs.get(CONTEXT_USAGE_KEY)
    assert isinstance(payload, dict)
    assert payload["input_tokens"] == 200
    assert 0 < sum(payload["segments"].values()) < 200


def test_resolve_prefers_memory_snapshot() -> None:
    mw = ContextUsageMiddleware()
    mw._snapshots["t1"] = ContextUsage(
        max_tokens=1000,
        used_tokens=42,
        input_tokens=42,
        output_tokens=1,
        segments={"conversation": 42},
        source="model_request",
    )
    resolved = resolve_context_usage(
        thread_id="t1",
        middleware=mw,
        messages=[],
        max_tokens=2000,
    )
    assert resolved.used_tokens == 42
    assert resolved.max_tokens == 2000


def test_resolve_without_override_preserves_routed_snapshot_cap() -> None:
    mw = ContextUsageMiddleware()
    mw._snapshots["t1"] = ContextUsage(
        max_tokens=1_000_000,
        used_tokens=42,
        input_tokens=42,
        segments={"conversation": 42},
        source="model_request",
    )

    resolved = resolve_context_usage(
        thread_id="t1",
        middleware=mw,
        messages=[],
        max_tokens=None,
    )

    assert resolved.max_tokens == 1_000_000


def test_resolve_falls_back_to_message_payload() -> None:
    ai = AIMessage(
        content="x",
        additional_kwargs={
            CONTEXT_USAGE_KEY: {
                "max_tokens": 1000,
                "used_tokens": 77,
                "input_tokens": 77,
                "output_tokens": 0,
                "segments": {"system_prompt": 77},
                "source": "model_request",
            }
        },
    )
    resolved = resolve_context_usage(
        thread_id="t2",
        middleware=None,
        messages=[ai],
        max_tokens=4096,
    )
    assert resolved.used_tokens == 77
    assert resolved.max_tokens == 4096
    assert resolved.segments["system_prompt"] == 77


@pytest.mark.asyncio
async def test_middleware_awrap_model_call() -> None:
    mw = ContextUsageMiddleware()
    request = MagicMock()
    request.system_message = SystemMessage(content="s" * 80)
    request.system_prompt = None
    request.tools = []
    request.messages = [HumanMessage(content="u")]
    request.runtime = None

    from langchain.agents.middleware import ModelResponse

    async def handler(_req: Any) -> ModelResponse:
        return ModelResponse(
            result=[
                AIMessage(
                    content="a",
                    usage_metadata={"input_tokens": 120, "output_tokens": 2, "total_tokens": 122},
                )
            ]
        )

    out = await mw.awrap_model_call(request, handler)
    assert CONTEXT_USAGE_KEY in out.result[0].additional_kwargs


def _snapshot(**overrides: Any) -> ContextUsage:
    base = {
        "max_tokens": 100_000,
        "used_tokens": 80_000,
        "input_tokens": 80_000,
        "output_tokens": 500,
        "uncached_input_tokens": 30_000,
        "cache_read_tokens": 50_000,
        "segments": {"system_prompt": 2_000, "conversation": 60_000},
        "source": "model_request",
    }
    base.update(overrides)
    return ContextUsage(**base)  # type: ignore[arg-type]


def test_shrink_context_usage_subtracts_from_conversation() -> None:
    shrunk = shrink_context_usage(_snapshot(), 20_000)
    assert shrunk.input_tokens == 60_000
    assert shrunk.used_tokens == 60_000
    assert shrunk.segments["conversation"] == 40_000
    # Untouched segments survive; stale per-call billing is cleared.
    assert shrunk.segments["system_prompt"] == 2_000
    assert shrunk.cache_read_tokens == 0
    assert shrunk.output_tokens == 0
    assert shrunk.max_tokens == 100_000


def test_shrink_context_usage_caps_at_conversation_size() -> None:
    """A delta larger than the conversation must not eat the other segments."""
    shrunk = shrink_context_usage(_snapshot(), 999_999)
    assert "conversation" not in shrunk.segments
    assert shrunk.input_tokens == 20_000  # 80k - 60k conversation
    assert shrunk.segments["system_prompt"] == 2_000


def test_shrink_context_usage_ignores_non_positive_delta() -> None:
    snap = _snapshot()
    assert shrink_context_usage(snap, 0) is snap
    assert shrink_context_usage(snap, -5) is snap


def test_shrink_snapshot_updates_stored_entry() -> None:
    mw = ContextUsageMiddleware()
    mw._snapshots["t1"] = _snapshot()
    updated = mw.shrink_snapshot("t1", removed_tokens=20_000)
    assert updated is not None
    assert updated.used_tokens == 60_000
    assert mw._snapshots["t1"].used_tokens == 60_000
    resolved = resolve_context_usage(thread_id="t1", middleware=mw, messages=[], max_tokens=None)
    assert resolved.used_tokens == 60_000


def test_shrink_snapshot_no_op_without_snapshot() -> None:
    mw = ContextUsageMiddleware()
    assert mw.shrink_snapshot("missing", removed_tokens=1_000) is None


def test_estimate_tokens_charges_more_for_cjk() -> None:
    """A flat len/4 under-counts Chinese by more than half."""
    latin = estimate_tokens("a" * 40)
    cjk = estimate_tokens("上" * 40)
    assert latin == 10
    assert cjk > 2 * latin


def test_estimate_json_tokens_is_denser_than_prose() -> None:
    blob = '{"name": "read_file", "parameters": {"path": "x"}}'
    assert estimate_json_tokens(blob) > estimate_tokens(blob)


def test_content_tokens_counts_full_tool_result() -> None:
    """message_content_text truncates for reading; the estimate must not."""
    payload = "x" * 12_000
    tokens = content_tokens([{"type": "tool_result", "output": payload}])
    assert tokens > 2_000
    # The reading rendition collapses to a short placeholder.
    assert estimate_tokens(message_content_text([{"type": "tool_result", "output": payload}])) < 50


def test_content_tokens_prices_media_blocks() -> None:
    assert content_tokens([{"type": "image_url", "image_url": "data:image/png;base64,zz"}]) > 500
    assert content_tokens([{"type": "file", "filename": "a.pdf"}]) > 100


def test_content_tokens_skips_thinking_blocks() -> None:
    """Providers strip reasoning from the history they re-send."""
    assert content_tokens([{"type": "thinking", "thinking": "y" * 4_000}]) == 0


def test_conversation_tokens_include_message_framing() -> None:
    one = conversation_tokens_from_messages([HumanMessage(content="hi")])
    two = conversation_tokens_from_messages([HumanMessage(content="hi"), HumanMessage(content="hi")])
    assert two - one == one  # same per-message cost, framing included
    assert one > estimate_tokens("hi")
