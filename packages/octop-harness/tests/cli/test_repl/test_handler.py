"""Tests for the stream event handler."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from io import StringIO
from typing import Any

from rich.console import Console

from octop_harness.cli.repl.handler import StreamEventHandler
from octop_harness.cli.repl.state import SessionState
from octop_harness.cli.ui.theme import get_theme


async def _events_from(events: list[dict[str, Any]]) -> AsyncGenerator[dict[str, Any], None]:
    for event in events:
        yield event


def test_handler_token_events() -> None:
    """Token events are rendered as streamed content with separator."""
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)
    theme = get_theme("dark")
    state = SessionState(session_id="test", model="m", agent_cfg={})

    events = [
        {"type": "token", "content": "Hello ", "node": "agent"},
        {"type": "token", "content": "world!", "node": "agent"},
    ]

    handler = StreamEventHandler(console, theme, state)
    asyncio.run(handler.handle_stream(_events_from(events)))

    printed = output.getvalue()
    assert "Hello" in printed
    assert "world!" in printed
    assert "─" in printed  # separator line
    assert "ctx:" in printed  # context usage


def test_handler_reasoning_events() -> None:
    """Reasoning events show summary after completion."""
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)
    theme = get_theme("dark")
    state = SessionState(session_id="test", model="m", agent_cfg={})

    events = [
        {"type": "reasoning", "content": "Let me think...", "node": "agent"},
        {"type": "token", "content": "The answer is 42.", "node": "agent"},
    ]

    handler = StreamEventHandler(console, theme, state)
    asyncio.run(handler.handle_stream(_events_from(events)))

    printed = output.getvalue()
    assert "⟡" in printed  # thinking summary
    assert "42" in printed


def test_handler_tool_call_events() -> None:
    """Tool call chunks and results are rendered."""
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)
    theme = get_theme("dark")
    state = SessionState(session_id="test", model="m", agent_cfg={})

    events = [
        {"type": "tool_call_chunk", "id": "tc1", "name": "web_search", "args": '"python"', "index": 0, "node": "agent"},
        {"type": "tool_result", "node": "tools", "messages": []},
        {"type": "token", "content": "Found results.", "node": "agent"},
    ]

    handler = StreamEventHandler(console, theme, state)
    asyncio.run(handler.handle_stream(_events_from(events)))

    printed = output.getvalue()
    assert "web_search" in printed
    assert "✓" in printed


def test_handler_empty_stream() -> None:
    """An empty stream does not crash."""
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)
    theme = get_theme("dark")
    state = SessionState(session_id="test", model="m", agent_cfg={})

    handler = StreamEventHandler(console, theme, state)
    asyncio.run(handler.handle_stream(_events_from([])))
    # Should not raise
