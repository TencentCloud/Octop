"""Rich Markdown streaming renderer for agent responses."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

if TYPE_CHECKING:
    from octop_harness.cli.ui.theme import Theme

# Fixed indentation: "  ● " = 4 chars, continuation = "    " (4 spaces)
_DOT_PREFIX = "  ● "
_CONT_PREFIX = "    "

# Blinking dot animation frames (bright ↔ dim cycle)
_DOT_FRAMES = ("●", "◉", "○", "◉")
_BLINK_INTERVAL = 0.35  # seconds between frames


class StreamRenderer:
    """Renders streaming text to the terminal, then re-renders as Markdown on finish.

    During streaming: the leading dot pulses (●→◉→○→◉) with raw text content.
    On finish: the Live display is replaced with a properly rendered Rich Markdown
    block (code highlighting, bold, lists, tables, etc.).

    Usage::

        renderer = StreamRenderer(console, theme)
        renderer.start()
        for chunk in agent_stream:
            renderer.feed(chunk)
        renderer.finish()
    """

    def __init__(self, console: Console, theme: Theme) -> None:
        self._console = console
        self._theme = theme
        self._buffer: str = ""
        self._live: Live | None = None
        self._start_time: float = 0.0
        self._started: bool = False

    @property
    def started(self) -> bool:
        """Whether the renderer has been started."""
        return self._started

    def start(self) -> None:
        """Begin a live-rendering session."""
        self._buffer = ""
        self._start_time = time.monotonic()
        self._started = True
        self._live = Live(
            "",
            console=self._console,
            refresh_per_second=12,
            transient=True,
        )
        self._live.start()

    def feed(self, text: str) -> None:
        """Append a text chunk and re-render with indentation."""
        self._buffer += text
        if self._live is not None and self._buffer.strip():
            self._live.update(self._render_indented())

    def finish(self) -> None:
        """End the live session and print the final Markdown-rendered output."""
        live = self._live
        self._live = None
        if live is not None:
            with contextlib.suppress(Exception):
                live.stop()

        # Render final content as Rich Markdown with indentation
        if self._buffer.strip():
            self._print_markdown(self._buffer.strip())

    def _print_markdown(self, text: str) -> None:
        """Render text as Rich Markdown, Claude Code style.

        Layout:
          ● First line of content
            Continuation indented by 4 spaces
        """
        md = Markdown(text, code_theme="monokai")
        # Render markdown to string, then prepend dot to first line
        with self._console.capture() as capture:
            self._console.print(md, highlight=False)
        rendered = capture.get()

        lines = rendered.rstrip("\n").split("\n")
        if lines:
            # First line: dot prefix
            self._console.print(
                f"  [{self._theme.dot_ai}]●[/] {lines[0]}",
                highlight=False,
            )
            # Remaining lines: continuation indent
            for line in lines[1:]:
                self._console.print(f"    {line}", highlight=False)

    def _render_indented(self) -> Text:
        """Build indented rich text for Live display with blinking dot."""
        elapsed = time.monotonic() - self._start_time
        frame_idx = int(elapsed / _BLINK_INTERVAL) % len(_DOT_FRAMES)
        dot_char = _DOT_FRAMES[frame_idx]

        lines = self._buffer.strip().split("\n")

        # Build Rich Text with styled blinking dot
        output = Text()
        output.append("  ")
        output.append(dot_char, style=self._theme.dot_ai)
        output.append(f" {lines[0]}")
        if len(lines) > 1:
            for line in lines[1:]:
                output.append(f"\n{_CONT_PREFIX}{line}")
        return output

    @property
    def content(self) -> str:
        """The accumulated raw text content."""
        return self._buffer
