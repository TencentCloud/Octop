"""Tests for agent runtime limit mapping."""

from __future__ import annotations

from octop.infra.agents.runtime_limits import (
    CONFIGURABLE_MAX_INPUT_TOKENS,
    CONFIGURABLE_MODEL_SETTINGS,
    agent_max_input_tokens,
    agent_model_settings,
    agent_recursion_limit,
    apply_agent_runtime_to_stream_request,
    resolve_context_max_tokens,
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
