"""Tests for slash command registry."""

from __future__ import annotations

import asyncio
from io import StringIO

from rich.console import Console

from octop_harness.cli.repl.commands import COMMANDS, dispatch_command
from octop_harness.cli.repl.slash_router import dispatch_slash, runtime_command_names
from octop_harness.cli.repl.state import SessionState
from octop_harness.cli.ui.theme import get_theme


def _make_state() -> SessionState:
    return SessionState(session_id="test1234abcd", model="openai/gpt-4", agent_cfg={"providers": {}})


def _dispatch_model(state: SessionState, console: Console, theme: object) -> None:
    asyncio.run(dispatch_slash("/model", state, console, theme))  # type: ignore[arg-type]


def test_help_command() -> None:
    output = StringIO()
    console = Console(file=output, force_terminal=True)
    theme = get_theme("dark")
    state = _make_state()
    dispatch_command("/help", state, console, theme)
    text = output.getvalue()
    assert "/help" in text
    assert "/exit" in text
    assert "/model" in text


def test_new_session() -> None:
    output = StringIO()
    console = Console(file=output, force_terminal=True)
    theme = get_theme("dark")
    state = _make_state()
    old_id = state.session_id
    dispatch_command("/new", state, console, theme)
    assert state.session_id != old_id
    assert len(state.session_id) == 32  # uuid hex


def test_exit_raises_system_exit() -> None:
    import pytest

    console = Console(file=StringIO(), force_terminal=True)
    theme = get_theme("dark")
    state = _make_state()
    with pytest.raises(SystemExit):
        dispatch_command("/exit", state, console, theme)


def test_quit_alias() -> None:
    import pytest

    console = Console(file=StringIO(), force_terminal=True)
    theme = get_theme("dark")
    state = _make_state()
    with pytest.raises(SystemExit):
        dispatch_command("/q", state, console, theme)


def test_unknown_command() -> None:
    output = StringIO()
    console = Console(file=output, force_terminal=True)
    theme = get_theme("dark")
    state = _make_state()
    dispatch_command("/foobar", state, console, theme)
    assert "Unknown" in output.getvalue()


def test_commands_registry_populated() -> None:
    assert "help" in COMMANDS
    assert "exit" in COMMANDS
    assert "new" in COMMANDS
    assert "clear" in COMMANDS
    assert "config" in COMMANDS
    assert "model" in runtime_command_names()
    assert "model" not in COMMANDS


def test_model_no_providers_prints_message() -> None:
    """When agent_cfg has no providers, prints 'No models configured'."""
    output = StringIO()
    console = Console(file=output, force_terminal=True)
    theme = get_theme("dark")
    state = SessionState(
        session_id="test1234abcd",
        model="openai/gpt-4",
        agent_cfg={"providers": {}},
    )
    _dispatch_model(state, console, theme)
    assert "no models" in output.getvalue().lower() or "not configured" in output.getvalue().lower()


def test_model_shows_numbered_list(monkeypatch: object) -> None:
    """When providers are configured, shows numbered list and switches on valid input."""
    from rich.prompt import Prompt

    output = StringIO()
    console = Console(file=output, force_terminal=True)
    theme = get_theme("dark")
    state = SessionState(
        session_id="test1234abcd",
        model="openai/gpt-4",
        agent_cfg={
            "providers": {
                "openai": {"models": [{"id": "gpt-4"}, {"id": "gpt-4o-mini"}]},
                "claude": {"models": [{"id": "claude-3-7-sonnet-20250219"}]},
            }
        },
    )
    monkeypatch.setattr(Prompt, "ask", staticmethod(lambda *a, **kw: "2"))  # type: ignore[attr-defined]

    _dispatch_model(state, console, theme)

    assert state.model == "openai/gpt-4o-mini"
    text = output.getvalue()
    assert "gpt-4" in text
    assert "gpt-4o-mini" in text
    assert "claude" in text


def test_model_single_model_shows_current() -> None:
    """When only one model is configured, just prints current model without prompt."""
    output = StringIO()
    console = Console(file=output, force_terminal=True)
    theme = get_theme("dark")
    state = SessionState(
        session_id="test1234abcd",
        model="openai/gpt-4",
        agent_cfg={"providers": {"openai": {"models": [{"id": "gpt-4"}]}}},
    )
    _dispatch_model(state, console, theme)
    assert "openai/gpt-4" in output.getvalue()
    assert state.model == "openai/gpt-4"  # unchanged


def test_model_cancel_on_empty_input(monkeypatch: object) -> None:
    """Pressing Enter (empty input) cancels without changing model."""
    from rich.prompt import Prompt

    output = StringIO()
    console = Console(file=output, force_terminal=True)
    theme = get_theme("dark")
    state = SessionState(
        session_id="test1234abcd",
        model="openai/gpt-4",
        agent_cfg={"providers": {"openai": {"models": [{"id": "gpt-4"}, {"id": "gpt-4o-mini"}]}}},
    )
    monkeypatch.setattr(Prompt, "ask", staticmethod(lambda *a, **kw: ""))  # type: ignore[attr-defined]

    _dispatch_model(state, console, theme)

    assert state.model == "openai/gpt-4"  # unchanged
    assert "cancel" in output.getvalue().lower()


def test_model_marks_current(monkeypatch: object) -> None:
    """Current model is marked with 'current' in the list."""
    from rich.prompt import Prompt

    output = StringIO()
    console = Console(file=output, force_terminal=True)
    theme = get_theme("dark")
    state = SessionState(
        session_id="test1234abcd",
        model="openai/gpt-4o-mini",
        agent_cfg={"providers": {"openai": {"models": [{"id": "gpt-4"}, {"id": "gpt-4o-mini"}]}}},
    )
    monkeypatch.setattr(Prompt, "ask", staticmethod(lambda *a, **kw: ""))  # type: ignore[attr-defined]

    _dispatch_model(state, console, theme)

    assert "current" in output.getvalue().lower()
