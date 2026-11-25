"""Tests for agent runtime limit mapping."""

from __future__ import annotations

from langchain.agents.middleware import ToolRetryMiddleware

from octop.infra.agents.middleware.consecutive_tool_call import ConsecutiveToolCallMiddleware
from octop.infra.agents.settings.runtime_limits import (
    CONFIGURABLE_MAX_INPUT_TOKENS,
    CONFIGURABLE_MODEL_SETTINGS,
    DEFAULT_MODEL_RETRY_MAX_RETRIES,
    DEFAULT_TOOL_CALL_RUN_LIMIT,
    DEFAULT_TOOL_RETRY_MAX_RETRIES,
    agent_max_input_tokens,
    agent_model_settings,
    agent_recursion_limit,
    apply_agent_runtime_to_stream_request,
    call_guard_middleware,
    resolve_context_max_tokens,
    resolve_model_retry,
    resolve_tool_call_run_limit,
    resolve_tool_retry,
)


def test_agent_recursion_limit_reads_max_iters() -> None:
    assert agent_recursion_limit({"max_iters": 42}) == 42
    assert agent_recursion_limit({"max_iters": "7"}) == 7
    assert agent_recursion_limit({}) is None


def test_agent_max_input_tokens_reads_max_input_length() -> None:
    assert agent_max_input_tokens({"max_input_length": 200_000}) == 200_000
    assert agent_max_input_tokens({"max_input_length": 0}) is None


def test_resolve_context_max_tokens_prefers_agent_override() -> None:
    assert resolve_context_max_tokens({"max_input_length": 64_000}, fallback=128_000) == 64_000
    assert resolve_context_max_tokens({}, fallback=96_000) == 96_000


def test_agent_model_settings_maps_generation_knobs() -> None:
    assert agent_model_settings(
        {
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 4096,
        }
    ) == {
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 4096,
    }
    assert agent_model_settings({}) == {}


def test_agent_temperature_and_top_p_validate_ranges() -> None:
    assert agent_model_settings({"temperature": 0}) == {"temperature": 0.0}
    assert agent_model_settings({"temperature": 3}) == {}
    assert agent_model_settings({"top_p": 1}) == {"top_p": 1.0}
    assert agent_model_settings({"top_p": 1.5}) == {}


def test_apply_agent_runtime_to_stream_request_merges_configurable() -> None:
    req = apply_agent_runtime_to_stream_request(
        {"messages": "hi", "configurable": {"model_settings": {"temperature": 1.0}}},
        {
            "max_iters": 12,
            "temperature": 0.2,
            "top_p": 0.95,
            "max_tokens": 2048,
            "max_input_length": 32000,
        },
    )
    assert req["recursion_limit"] == 12
    assert req["configurable"][CONFIGURABLE_MODEL_SETTINGS] == {
        "temperature": 0.2,
        "top_p": 0.95,
        "max_tokens": 2048,
    }
    assert req["configurable"][CONFIGURABLE_MAX_INPUT_TOKENS] == 32000


def test_call_guard_defaults_cap_repeated_tool_calls_and_retry_tool_exceptions() -> None:
    assert resolve_tool_call_run_limit({}) == DEFAULT_TOOL_CALL_RUN_LIMIT
    assert resolve_model_retry({}).enabled is True
    assert resolve_model_retry({}).max_retries == DEFAULT_MODEL_RETRY_MAX_RETRIES
    assert resolve_tool_retry({}).enabled is True
    assert resolve_tool_retry({}).max_retries == DEFAULT_TOOL_RETRY_MAX_RETRIES

    middleware = call_guard_middleware({})
    limit = next(item for item in middleware if isinstance(item, ConsecutiveToolCallMiddleware))
    tool_retry = next(item for item in middleware if isinstance(item, ToolRetryMiddleware))
    assert limit.limit == DEFAULT_TOOL_CALL_RUN_LIMIT
    assert tool_retry.max_retries == DEFAULT_TOOL_RETRY_MAX_RETRIES
    assert tool_retry.initial_delay == 1.0
    assert tool_retry.max_delay == 60.0
    assert tool_retry.on_failure == "continue"


def test_call_guard_honors_overrides_and_can_be_disabled() -> None:
    cfg = {
        "tool_call_run_limit": 12,
        "model_retry_enabled": False,
        "model_retry_max_retries": 0,
        "tool_retry_max_retries": 1,
        "tool_retry_initial_delay": 0.5,
        "tool_retry_max_delay": 2,
    }
    assert resolve_tool_call_run_limit(cfg) == 12
    assert resolve_model_retry(cfg).enabled is False
    assert resolve_model_retry(cfg).max_retries == 0
    tool_retry = resolve_tool_retry(cfg)
    assert tool_retry.max_retries == 1
    assert tool_retry.initial_delay == 0.5
    assert tool_retry.max_delay == 2.0

    disabled = call_guard_middleware(
        {"tool_call_limit_enabled": False, "tool_retry_enabled": False}
    )
    assert disabled == []
    assert (
        resolve_tool_call_run_limit({"tool_call_limit_enabled": False, "tool_call_run_limit": 3})
        is None
    )
