"""Stream event handler — consumes agent.stream() and dispatches rendering."""

from __future__ import annotations

import contextlib
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.live import Live
from rich.text import Text

from octop_harness.cli.ui.renderer import StreamRenderer

if TYPE_CHECKING:
    from octop_harness.cli.repl.state import SessionState
    from octop_harness.cli.ui.theme import Theme

# Spinner frames for the working status
_SPINNER_FRAMES = ("·", "•", "●", "•")
_SPINNER_INTERVAL = 0.4


class StreamEventHandler:
    """Consumes stream events from agent.stream() and renders to terminal.

    Uses a single Live line for all "working" states (thinking + tools).
    Only the final content (token stream) breaks out of the Live into
    the StreamRenderer.
    """

    def __init__(self, console: Console, theme: Theme, state: SessionState) -> None:
        self._console = console
        self._theme = theme
        self._state = state
        self._renderer: StreamRenderer | None = None
        # Unified working status Live — covers thinking AND tools
        self._status_live: Live | None = None
        self._status_start: float = 0.0
        self._thinking_tokens: int = 0
        self._is_thinking: bool = False
        # Tool tracking (cumulative across all rounds in one turn)
        self._tool_calls: dict[str, _ToolCallState] = {}
        self._tool_count: int = 0
        self._tool_max_elapsed: float = 0.0
        self._tool_names: list[str] = []
        self._current_running_tool: str = ""
        self._start_time: float = 0.0

    async def handle_stream(self, stream: AsyncGenerator[dict[str, Any], None]) -> None:
        """Main dispatch loop over stream events."""
        self._start_time = time.monotonic()
        self._renderer = None
        self._status_live = None
        self._status_start = 0.0
        self._thinking_tokens = 0
        self._is_thinking = False
        self._tool_calls = {}
        self._tool_count = 0
        self._tool_max_elapsed = 0.0
        self._tool_names = []
        self._current_running_tool = ""

        try:
            async for event in stream:
                event_type = event.get("type", "")
                match event_type:
                    case "reasoning":
                        self._handle_reasoning(event)
                    case "token":
                        self._handle_token(event)
                    case "tool_call_chunk":
                        self._handle_tool_call_chunk(event)
                    case "tool_result":
                        self._handle_tool_result(event)
                    case "state_snapshot":
                        self._handle_state_snapshot(event)
                    case "state_update":
                        pass  # silent
                    case "custom":
                        self._handle_custom(event)
        finally:
            self._finalize()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _handle_reasoning(self, event: dict[str, Any]) -> None:
        """Feed reasoning content into the unified status Live."""
        self._is_thinking = True
        self._current_running_tool = ""
        content = event.get("content", "")
        self._thinking_tokens += len(content.split())
        self._ensure_status_live()
        self._refresh_status()

    def _handle_token(self, event: dict[str, Any]) -> None:
        """Stop status Live and feed the stream renderer."""
        self._is_thinking = False
        # Just stop the Live silently — don't print static summary yet.
        # The summary will be printed in _finalize after the stream ends.
        self._dismiss_status_live()

        if self._renderer is None:
            self._renderer = StreamRenderer(self._console, self._theme)
            self._renderer.start()
        self._renderer.feed(event.get("content", ""))

    def _handle_tool_call_chunk(self, event: dict[str, Any]) -> None:
        """Track tool calls and update the unified status Live."""
        tool_id = event.get("id", "")
        if not tool_id:
            return

        if tool_id not in self._tool_calls:
            self._is_thinking = False
            if self._renderer is not None:
                self._renderer.finish()
                self._renderer = None

            name = event.get("name", "unknown")
            self._tool_calls[tool_id] = _ToolCallState(
                name=name,
                args_buffer=event.get("args", ""),
                start_time=time.monotonic(),
            )
            self._current_running_tool = name
            self._ensure_status_live()
            self._refresh_status()
        else:
            self._tool_calls[tool_id].args_buffer += event.get("args", "")

    def _handle_tool_result(self, event: dict[str, Any]) -> None:
        """Mark tools complete and update the unified status Live."""
        for _tool_id, tc in list(self._tool_calls.items()):
            if not tc.completed:
                tc.completed = True
                tc.elapsed = time.monotonic() - tc.start_time
                self._tool_count += 1
                self._tool_max_elapsed = max(self._tool_max_elapsed, tc.elapsed)
                self._tool_names.append(tc.name)

        self._current_running_tool = ""
        # Clear batch for next round
        self._tool_calls = {}
        # Update status to show completed summary
        self._refresh_status()

    def _handle_state_snapshot(self, event: dict[str, Any]) -> None:
        """Extract token usage from state snapshot."""
        data = event.get("data", {})
        if not isinstance(data, dict):
            return
        messages = data.get("messages", [])
        if messages:
            last = messages[-1]
            usage_meta = getattr(last, "usage_metadata", None)
            if isinstance(usage_meta, dict):
                inp = usage_meta.get("input_tokens", 0) or usage_meta.get("prompt_tokens", 0)
                out = usage_meta.get("output_tokens", 0) or usage_meta.get("completion_tokens", 0)
                if inp or out:
                    elapsed = time.monotonic() - self._start_time
                    self._state.update_usage(input_tokens=int(inp), output_tokens=int(out), elapsed=elapsed)

    def _handle_custom(self, event: dict[str, Any]) -> None:
        """Render custom events as system messages."""
        data = event.get("data", "")
        content = str(data) if data else ""
        if content:
            self._console.print(f"  [{self._theme.dot_info}]●[/] {content}")

    # ------------------------------------------------------------------
    # Unified status Live management
    # ------------------------------------------------------------------

    def _ensure_status_live(self) -> None:
        """Start the status Live if not already running."""
        if self._status_live is None:
            self._status_start = time.monotonic()
            self._status_live = Live(
                "",
                console=self._console,
                refresh_per_second=8,
                transient=True,
            )
            self._status_live.start()

    def _refresh_status(self) -> None:
        """Update the status Live with current state."""
        if self._status_live is None:
            return

        elapsed = time.monotonic() - self._status_start
        output = Text()
        output.append("  ")

        if self._current_running_tool:
            # Tool is running
            frame_idx = int(elapsed / _SPINNER_INTERVAL) % len(_SPINNER_FRAMES)
            output.append(_SPINNER_FRAMES[frame_idx], style=self._theme.dot_tool)
            output.append(f" {self._current_running_tool}…", style="dim")
            if self._tool_count > 0:
                output.append(f" ({self._tool_count} done, {elapsed:.0f}s)", style="dim")
        elif self._is_thinking:
            # Thinking
            frame_idx = int(elapsed / _SPINNER_INTERVAL) % len(_SPINNER_FRAMES)
            output.append(_SPINNER_FRAMES[frame_idx], style=self._theme.dot_thinking)
            output.append(" Thinking…", style=self._theme.dot_thinking)
            parts = [f"{elapsed:.0f}s"]
            if self._thinking_tokens > 0:
                parts.append(f"↓ {self._thinking_tokens} tokens")
            if self._tool_count > 0:
                parts.append(f"{self._tool_count} tools done")
            output.append(f" ({' · '.join(parts)})", style="dim")
        elif self._tool_count > 0:
            # All tools done, waiting for next event
            output.append("✓", style="dim")
            if self._tool_count == 1:
                output.append(f" {self._tool_names[0]} ({self._tool_max_elapsed:.1f}s)", style="dim")
            else:
                names = ", ".join(self._tool_names)
                output.append(
                    f" {self._tool_count} tools ran ({self._tool_max_elapsed:.1f}s) — {names}",
                    style="dim",
                )

        self._status_live.update(output)

    def _dismiss_status_live(self) -> None:
        """Stop the status Live silently (transient erases it, no static print)."""
        if self._status_live is not None:
            with contextlib.suppress(Exception):
                self._status_live.stop()
            self._status_live = None

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------

    def _finalize(self) -> None:
        """Cleanup: stop status, finish renderer, print stats."""
        # Stop Live if still running
        if self._status_live is not None:
            with contextlib.suppress(Exception):
                self._status_live.stop()
            self._status_live = None

        # Print work summary BEFORE content
        self._print_work_summary()

        if self._renderer is not None:
            self._renderer.finish()
            self._renderer = None

        elapsed = time.monotonic() - self._start_time
        self._state.last_elapsed = elapsed

        self._console.print()
        self._print_turn_footer(elapsed)
        self._console.print()

    def _print_work_summary(self) -> None:
        """Print a static one-line summary of thinking + tools work done."""
        if self._tool_count == 0 and self._thinking_tokens == 0:
            return  # nothing to summarize

        parts: list[str] = []

        # Thinking summary
        if self._thinking_tokens > 0:
            elapsed = time.monotonic() - self._status_start
            parts.append(f"⟡ {elapsed:.1f}s")

        # Tools summary
        if self._tool_count == 1:
            parts.append(f"✓ {self._tool_names[0]} ({self._tool_max_elapsed:.1f}s)")
        elif self._tool_count > 1:
            names = ", ".join(self._tool_names)
            parts.append(f"✓ {self._tool_count} tools ({self._tool_max_elapsed:.1f}s) — {names}")

        if parts:
            summary = " · ".join(parts)
            self._console.print(f"  [dim]{summary}[/]", highlight=False)
            self._console.print()

    def _print_turn_footer(self, elapsed: float) -> None:
        """Print the turn separator and token/context stats."""
        width = min(self._console.width, 50)
        separator = "─" * width
        self._console.print(f"  [{self._theme.separator_style}]{separator}[/]")

        parts: list[str] = []

        if self._state.total_tokens > 0:
            from octop_harness.cli.ui.token_bar import _format_k

            in_k = _format_k(self._state.input_tokens)
            out_k = _format_k(self._state.output_tokens)
            parts.append(f"↑{in_k} ↓{out_k}")

        parts.append(f"{elapsed:.1f}s")

        total = self._state.total_tokens
        max_t = self._state.max_tokens
        if max_t > 0:
            from octop_harness.cli.ui.token_bar import _format_k

            total_k = _format_k(total)
            max_k = _format_k(max_t)
            pct = int(total / max_t * 100) if max_t else 0
            parts.append(f"ctx: {total_k}/{max_k} ({pct}%)")

        stats_line = " │ ".join(parts)
        self._console.print(f"  [dim]{stats_line}[/]")

    @staticmethod
    def _summarize_args(args_json: str) -> str:
        """Extract a short summary from tool call args JSON."""
        import json

        with contextlib.suppress(Exception):
            parsed = json.loads(args_json)
            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, str) and v:
                        return v[:40] + ("..." if len(v) > 40 else "")
        clean = args_json.strip('"').strip()
        if len(clean) > 40:
            return clean[:40] + "..."
        return clean if clean else "..."


class _ToolCallState:
    """Internal state for a single in-flight tool call."""

    __slots__ = ("args_buffer", "completed", "elapsed", "name", "start_time")

    def __init__(self, name: str, args_buffer: str, start_time: float) -> None:
        self.name = name
        self.args_buffer = args_buffer
        self.start_time = start_time
        self.completed = False
        self.elapsed: float = 0.0
