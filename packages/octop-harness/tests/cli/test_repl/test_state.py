"""Tests for SessionState."""

from octop_harness.cli.repl.state import SessionState


def test_session_state_defaults() -> None:
    state = SessionState(session_id="abc123", model="openai/gpt-4", agent_cfg={})
    assert state.session_id == "abc123"
    assert state.model == "openai/gpt-4"
    assert state.input_tokens == 0
    assert state.output_tokens == 0
    assert state.max_tokens == 128_000
    assert state.last_elapsed == 0.0


def test_session_state_total_tokens() -> None:
    state = SessionState(session_id="x", model="m", agent_cfg={})
    state.input_tokens = 1000
    state.output_tokens = 500
    assert state.total_tokens == 1500


def test_session_state_update_usage() -> None:
    state = SessionState(session_id="x", model="m", agent_cfg={})
    state.update_usage(input_tokens=2000, output_tokens=800, elapsed=1.5)
    assert state.input_tokens == 2000
    assert state.output_tokens == 800
    assert state.last_elapsed == 1.5
