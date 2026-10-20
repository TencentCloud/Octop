"""Tests for the prompt_toolkit bottom toolbar formatter."""

from octop_harness.cli.repl.state import SessionState
from octop_harness.cli.ui.toolbar import format_toolbar


def test_format_toolbar_basic() -> None:
    state = SessionState(session_id="abcdef1234567890", model="openai/gpt-4", agent_cfg={})
    result = format_toolbar(state)
    assert "openai/gpt-4" in result
    assert "abcdef12" in result  # first 8 chars of session_id
    assert "ctx:" in result  # always shows context


def test_format_toolbar_with_usage() -> None:
    state = SessionState(session_id="abcdef1234567890", model="deepseek/chat", agent_cfg={})
    state.update_usage(input_tokens=36000, output_tokens=2000, elapsed=2.1)
    result = format_toolbar(state)
    assert "deepseek/chat" in result
    assert "2.1s" in result
    assert "ctx:" in result
    assert "128k" in result  # max tokens shown


def test_format_toolbar_shows_context_percentage() -> None:
    state = SessionState(session_id="abcdef1234567890", model="m", agent_cfg={}, max_tokens=100_000)
    state.update_usage(input_tokens=25000, output_tokens=5000, elapsed=1.0)
    result = format_toolbar(state)
    assert "30%" in result  # 30k / 100k = 30%
    assert "ctx:" in result


def test_format_toolbar_no_elapsed() -> None:
    state = SessionState(session_id="abc123", model="m", agent_cfg={})
    result = format_toolbar(state)
    # Should not crash when elapsed=0
    assert "m" in result
    assert "ctx:" in result
