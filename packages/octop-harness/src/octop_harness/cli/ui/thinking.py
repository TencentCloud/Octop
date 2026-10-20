"""ThinkingRenderer — animated status line during reasoning, Claude Code style."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live
from rich.text import Text

if TYPE_CHECKING:
    from octop_harness.cli.ui.theme import Theme

# Spinner animation frames
_SPINNER_FRAMES = ("·", "•", "●", "•")
_SPINNER_INTERVAL = 0.4  # seconds between frames

# Status messages that rotate during long thinking
_STATUS_MESSAGES = (
    "thinking",
    "still thinking",
    "pondering",
    "reasoning",
)


class ThinkingRenderer:
    """Displays an animated status line during AI reasoning/thinking.

    Shows a live-updating line like Claude Code:
        · Pondering… (3s · ↓ 42 tokens · still thinking)

    On collapse, replaces with a static summary:
        ⟡ Thought for 3.1s

    Usage::

        renderer = ThinkingRenderer(console, theme)
        renderer.start()
        for chunk in reasoning_stream:
            renderer.feed(chunk)
        renderer.collapse()
    """

    def __init__(self, console: Console, theme: Theme) -> None:
        self._console = console
        self._theme = theme
        self._buffer: str = ""
        self._live: Live | None = None
        self._start_time: float = 0.0
        self._token_count: int = 0

    @property
    def content(self) -> str:
        """Raw accumulated thinking text."""
        return self._buffer

    @property
    def is_active(self) -> bool:
        """Whether the renderer is currently streaming."""
        return self._live is not None

    def start(self) -> None:
        """Begin a live-rendering session for thinking content."""
        self._buffer = ""
        self._token_count = 0
        self._start_time = time.monotonic()
        self._live = Live(
            self._render_status(),
            console=self._console,
            refresh_per_second=8,
            transient=True,
        )
        self._live.start()

    def feed(self, text: str) -> None:
        """Append a text chunk and update the status display."""
        self._buffer += text
        # Count tokens roughly (whitespace-separated words)
        self._token_count += len(text.split())
        if self._live is not None:
            self._live.update(self._render_status())

    def collapse(self) -> None:
        """End live display and print a one-line summary."""
        live = self._live
        self._live = None
        if live is None:
            return
        with contextlib.suppress(Exception):
            live.stop()
        elapsed = time.monotonic() - self._start_time
        self._console.print(f"  [{self._theme.dot_thinking}]⟡[/] [dim]Thought for {elapsed:.1f}s[/]")
        self._console.print()  # spacing after thinking

    def _render_status(self) -> Text:
        """Build the animated status line."""
        elapsed = time.monotonic() - self._start_time

        # Spinner animation
        frame_idx = int(elapsed / _SPINNER_INTERVAL) % len(_SPINNER_FRAMES)
        spinner = _SPINNER_FRAMES[frame_idx]

        # Rotating status message (changes every 4 seconds)
        msg_idx = int(elapsed / 4.0) % len(_STATUS_MESSAGES)
        status_msg = _STATUS_MESSAGES[msg_idx]

        # Build the status line
        output = Text()
        output.append("  ")
        output.append(spinner, style=self._theme.dot_thinking)
        output.append(" Thinking", style=f"{self._theme.dot_thinking}")
        output.append("… ", style="dim")
        output.append("(", style="dim")
        output.append(f"{elapsed:.0f}s", style="dim")
        if self._token_count > 0:
            output.append(f" · ↓ {self._token_count} tokens", style="dim")
        output.append(f" · {status_msg}", style="dim italic")
        output.append(")", style="dim")
        return output
