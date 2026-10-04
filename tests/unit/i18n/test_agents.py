"""Tests for agents i18n domain."""

from __future__ import annotations

from octop.i18n.domains.agents import (
    AGENT_START_TIMEOUT,
    MODEL_REF_UNAVAILABLE,
    NO_MODELS_CONFIGURED,
    agent_error_message,
    agent_state_label,
)


def test_agent_state_label_failed_zh() -> None:
    assert agent_state_label("failed", "zh") == "启动失败"


def test_agent_state_label_failed_en() -> None:
    assert agent_state_label("failed", "en") == "Start failed"


def test_agent_state_label_unknown_state_passthrough() -> None:
    assert agent_state_label("custom", "en") == "custom"


def test_agent_error_message_octop_key_zh() -> None:
    assert "管理" in agent_error_message(NO_MODELS_CONFIGURED, "zh")


def test_agent_error_message_model_ref_key_zh() -> None:
    assert "默认模型" in agent_error_message(MODEL_REF_UNAVAILABLE, "zh")


def test_agent_error_message_start_timeout_zh() -> None:
    assert "超时" in agent_error_message(AGENT_START_TIMEOUT, "zh")


def test_agent_error_message_raw_harness_zh() -> None:
    msg = "Unknown provider 'x' in model ref 'x/y'"
    assert "默认模型" in agent_error_message(msg, "zh")


def test_classify_no_enabled_models() -> None:
    from octop.i18n.domains.agents import classify_agent_start_error_message

    assert (
        classify_agent_start_error_message("No enabled models found in providers")
        == NO_MODELS_CONFIGURED
    )


def test_classify_unknown_provider() -> None:
    from octop.i18n.domains.agents import classify_agent_start_error_message

    msg = "Unknown provider 'missing' in model ref 'missing/gpt-4'"
    assert classify_agent_start_error_message(msg) == MODEL_REF_UNAVAILABLE
