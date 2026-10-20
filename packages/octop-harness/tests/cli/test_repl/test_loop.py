"""Tests for the REPL main loop."""

from __future__ import annotations

import asyncio
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

from rich.console import Console

from octop_harness.cli.repl.loop import print_welcome, run
from octop_harness.cli.repl.state import SessionState
from octop_harness.cli.ui.theme import get_theme


def test_print_welcome() -> None:
    """Welcome banner shows model, session, and project info."""
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=80)
    theme = get_theme("dark")
    state = SessionState(
        session_id="abcdef1234567890abcdef1234567890",
        model="openai/gpt-4",
        agent_cfg={},
    )
    print_welcome(console, theme, state, project_dir="/workspace/my-project", config_found=True)
    printed = output.getvalue()
    assert "openai/gpt-4" in printed
    assert "abcdef12" in printed  # first 8 chars of session_id
    assert "/workspace/my-project" in printed
    assert "╦" in printed  # ASCII banner present
    assert "╩" in printed


def test_run_exits_on_eof() -> None:
    """REPL exits cleanly when prompt raises EOFError."""
    mock_session = MagicMock()
    mock_session.prompt_async = AsyncMock(side_effect=EOFError)

    agent_cfg = {"providers": {"test": {"base_url": "http://x", "api_key": "k", "models": [{"id": "m"}]}}}
    cli_cfg = {"theme": "dark", "context_window_tokens": 128_000}

    with (
        patch("octop_harness.cli.repl.loop.create_prompt_session", return_value=mock_session),
        patch("octop_harness.cli.repl.loop._create_agent", return_value=MagicMock()),
    ):
        # Should not raise
        asyncio.run(run(agent_cfg, cli_cfg, model="openai/gpt-4", session_id="test123"))


def test_run_dispatches_slash_command() -> None:
    """Slash commands are routed to dispatch_command."""
    call_count = 0

    async def _prompt_side_effect(*args: object, **kwargs: object) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "/model"
        raise EOFError

    mock_session = MagicMock()
    mock_session.prompt_async = AsyncMock(side_effect=_prompt_side_effect)

    agent_cfg = {"providers": {"test": {"base_url": "http://x", "api_key": "k", "models": [{"id": "m"}]}}}
    cli_cfg = {"theme": "dark", "context_window_tokens": 128_000}

    with (
        patch("octop_harness.cli.repl.loop.create_prompt_session", return_value=mock_session),
        patch("octop_harness.cli.repl.loop._create_agent", return_value=MagicMock()),
        patch("octop_harness.cli.repl.loop.dispatch_slash") as mock_dispatch,
    ):
        asyncio.run(run(agent_cfg, cli_cfg, model="openai/gpt-4", session_id="test123"))
        mock_dispatch.assert_called_once()
        # First arg should be the command string
        assert mock_dispatch.call_args[0][0] == "/model"
