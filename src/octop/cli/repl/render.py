"""Terminal rendering for harness stream chunks (CLI chat)."""

from __future__ import annotations

import contextlib
import sys
import time
from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

_SPINNER_FRAMES = ("·", "•", "●", "•")
_SPINNER_INTERVAL = 0.4


@dataclass(frozen=True)
class ChatTheme:
    dot_ai: str = "bold green"
    dot_tool: str = "bold yellow"
    dot_thinking: str = "bold magenta"
    dot_error: str = "bold red"
    separator_style: str = "dim"


class _ToolCallState:
    __slots__ = ("args_buffer", "completed", "elapsed", "name", "start_time")

    def __init__(self, name: str, args_buffer: str, start_time: float) -> None:
        self.name = name
        self.args_buffer = args_buffer
        self.start_time = start_time
        self.completed = False
        self.elapsed = 0.0


class ChunkRenderer:
    """Consume harness chunks and render to the terminal (sync, Rich-based)."""

    def __init__(
        self,
        *,
        console: Console | None = None,
        theme: ChatTheme | None = None,
        plain: bool = False,
        markdown: bool = True,
    ) -> None:
        self._console = console or Console(file=sys.stdout)
        self._theme = theme or ChatTheme()
        self._plain = plain
        self._markdown = markdown and not plain
        self._token_buffer = ""
        self._status_live: Live | None = None
        self._stream_live: Live | None = None
        self._status_start = 0.0
        self._thinking = False
        self._thinking_tokens = 0
        self._tool_calls: dict[str, _ToolCallState] = {}
        self._tool_count = 0
        self._tool_max_elapsed = 0.0
        self._tool_names: list[str] = []
        self._current_tool = ""
        self._turn_start = 0.0
        self._had_output = False
        self._last_elapsed = 0.0

    @property
    def last_elapsed(self) -> float:
        return self._last_elapsed

    def begin_turn(self) -> None:
        self._token_buffer = ""
        self._turn_start = time.monotonic()
        self._thinking = False
        self._thinking_tokens = 0
        self._tool_calls = {}
        self._tool_count = 0
        self._tool_max_elapsed = 0.0
        self._tool_names = []
        self._current_tool = ""
        self._had_output = False

    def feed(self, chunk: dict[str, Any]) -> None:
        ctype = chunk.get("type")
        if ctype in ("token", "delta"):
            self._dismiss_status()
            text = str(chunk.get("content", chunk.get("text", "")))
            if text:
                self._token_buffer += text
                if self._markdown:
                    self._ensure_stream_live()
                    self._refresh_stream_live()
                else:
                    sys.stdout.write(text)
                    sys.stdout.flush()
                self._had_output = True
        elif ctype == "reasoning":
            self._thinking = True
            self._current_tool = ""
            content = str(chunk.get("content", ""))
            self._thinking_tokens += len(content.split()) if content else 0
            self._ensure_status()
            self._refresh_status()
        elif ctype in ("tool_call_chunk", "tool_start"):
            self._handle_tool(chunk)
        elif ctype in ("tool_result", "tool_end"):
            self._handle_tool_result()
        elif ctype == "error":
            self._dismiss_status()
            self._console.print(
                f"  [{self._theme.dot_error}]●[/] {chunk.get('message', 'error')}",
                highlight=False,
            )
        elif ctype == "slash_action":
            action = str(chunk.get("action", ""))
            detail = chunk.get("agent_id") or chunk.get("thread_id") or ""
            suffix = f" ({detail})" if detail else ""
            self._console.print(f"  [dim]→ {action}{suffix}[/]", highlight=False)
        elif ctype == "hitl_required":
            self._print_hitl_pause(chunk)
        elif ctype == "done":
            pass

    @property
    def token_buffer(self) -> str:
        return self._token_buffer

    def finish_turn(self) -> None:
        self._dismiss_status()
        self._dismiss_stream_live(final=True)
        if self._plain and self._token_buffer.strip():
            sys.stdout.write("\n")
            sys.stdout.flush()
        elif not self._had_output and (self._tool_count or self._thinking_tokens):
            self._print_work_summary()
        self._last_elapsed = time.monotonic() - self._turn_start
        self._print_footer()

    def _ensure_stream_live(self) -> None:
        if self._stream_live is None:
            self._stream_live = Live(
                "",
                console=self._console,
                refresh_per_second=12,
                transient=True,
            )
            self._stream_live.start()

    def _refresh_stream_live(self) -> None:
        if self._stream_live is None or not self._token_buffer:
            return
        self._stream_live.update(Markdown(self._token_buffer, code_theme="monokai"))

    def _dismiss_stream_live(self, *, final: bool = False) -> None:
        if self._stream_live is None:
            if final and self._markdown and self._token_buffer.strip():
                render_markdown_reply(self._token_buffer, theme=self._theme, console=self._console)
            return
        with contextlib.suppress(Exception):
            self._stream_live.stop()
        self._stream_live = None
        if final and self._markdown and self._token_buffer.strip():
            render_markdown_reply(self._token_buffer, theme=self._theme, console=self._console)

    def _handle_tool(self, chunk: dict[str, Any]) -> None:
        from octop.cli.support.db import resolve_cli_locale
        from octop.i18n import tool_display_name

        tool_id = str(chunk.get("id") or chunk.get("call_id") or "")
        if tool_id and tool_id in self._tool_calls:
            self._tool_calls[tool_id].args_buffer += str(chunk.get("args", ""))
            return

        raw = chunk.get("display_name") or chunk.get("name", "tool")
        locale = resolve_cli_locale()
        label = (
            str(raw)
            if chunk.get("display_name")
            else tool_display_name(str(raw) if raw else None, locale)
        )
        self._thinking = False
        self._dismiss_status()
        if tool_id:
            self._tool_calls[tool_id] = _ToolCallState(
                name=label,
                args_buffer=str(chunk.get("args", "")),
                start_time=time.monotonic(),
            )
        self._current_tool = label
        self._ensure_status()
        self._refresh_status()

    def _handle_tool_result(self) -> None:
        for tc in list(self._tool_calls.values()):
            if not tc.completed:
                tc.completed = True
                tc.elapsed = time.monotonic() - tc.start_time
                self._tool_count += 1
                self._tool_max_elapsed = max(self._tool_max_elapsed, tc.elapsed)
                self._tool_names.append(tc.name)
        self._tool_calls = {}
        self._current_tool = ""
        self._refresh_status()

    def _ensure_status(self) -> None:
        if self._status_live is None:
            self._status_start = time.monotonic()
            self._status_live = Live(
                "", console=self._console, refresh_per_second=8, transient=True
            )
            self._status_live.start()

    def _refresh_status(self) -> None:
        if self._status_live is None:
            return
        elapsed = time.monotonic() - self._status_start
        out = Text()
        out.append("  ")
        if self._current_tool:
            idx = int(elapsed / _SPINNER_INTERVAL) % len(_SPINNER_FRAMES)
            out.append(_SPINNER_FRAMES[idx], style=self._theme.dot_tool)
            out.append(f" {self._current_tool}…", style="dim")
        elif self._thinking:
            idx = int(elapsed / _SPINNER_INTERVAL) % len(_SPINNER_FRAMES)
            out.append(_SPINNER_FRAMES[idx], style=self._theme.dot_thinking)
            out.append(" Thinking…", style=self._theme.dot_thinking)
        elif self._tool_count:
            out.append("✓", style="dim")
            if self._tool_count == 1:
                out.append(f" {self._tool_names[0]} ({self._tool_max_elapsed:.1f}s)", style="dim")
            else:
                names = ", ".join(self._tool_names)
                out.append(
                    f" {self._tool_count} tools ({self._tool_max_elapsed:.1f}s) — {names}",
                    style="dim",
                )
        self._status_live.update(out)

    def _dismiss_status(self) -> None:
        if self._status_live is not None:
            with contextlib.suppress(Exception):
                self._status_live.stop()
            self._status_live = None

    def _print_work_summary(self) -> None:
        parts: list[str] = []
        if self._thinking_tokens:
            parts.append(f"⟡ {time.monotonic() - self._status_start:.1f}s")
        if self._tool_count == 1:
            parts.append(f"✓ {self._tool_names[0]} ({self._tool_max_elapsed:.1f}s)")
        elif self._tool_count > 1:
            parts.append(
                f"✓ {self._tool_count} tools ({self._tool_max_elapsed:.1f}s) — {', '.join(self._tool_names)}"
            )
        if parts:
            self._console.print(f"  [dim]{' · '.join(parts)}[/]", highlight=False)

    def _print_hitl_pause(self, chunk: dict[str, Any]) -> None:
        from octop.cli.support.db import resolve_cli_locale

        card = format_cli_hitl_pause(chunk, locale=resolve_cli_locale())
        if not card:
            return
        self._dismiss_status()
        self._console.print()
        if self._markdown:
            self._console.print(Markdown(card, code_theme="monokai"), highlight=False)
        else:
            self._console.print(card, highlight=False)
        self._console.print()
        self._had_output = True

    def _print_footer(self) -> None:
        elapsed = self._last_elapsed or (time.monotonic() - self._turn_start)
        width = min(self._console.width, 50)
        self._console.print(f"  [{self._theme.separator_style}]{'─' * width}[/]")
        self._console.print(f"  [dim]{elapsed:.1f}s[/]", highlight=False)
        self._console.print()


def format_cli_hitl_pause(chunk: dict[str, Any], *, locale: str = "zh") -> str:
    """Render a ``hitl_required`` chunk as the same card IM users see."""
    from octop.infra.gateway.hitl.format import format_hitl_card, parse_action_requests

    raw = chunk.get("request")
    request = raw if isinstance(raw, dict) else {}
    pending_id = str(chunk.get("pending_id") or request.get("pending_id") or "")
    return format_hitl_card(
        parse_action_requests(request),
        pending_id=pending_id or "—",
        locale=locale,
    )


def print_slash_help(*, locale: str = "zh", include_hitl_approval: bool = False) -> None:
    """Print slash commands visible to the CLI REPL."""
    import click

    from octop.infra.gateway.slash.catalog import list_specs

    commands = list_specs(origin="cli", include_hitl_approval=include_hitl_approval)
    if not commands:
        click.echo("  (no slash commands)")
        return
    click.echo("  Slash commands (also handled when sent in chat):")
    for spec in commands[:20]:
        label = spec.label_for(locale)
        usage = spec.usage or spec.command
        click.echo(f"    {usage:24s} {label}")
    if len(commands) > 20:
        click.echo(f"    … and {len(commands) - 20} more (see dashboard /help)")


def print_welcome(*, agent_id: str, model: str, session_key: str, thread_id: str | None) -> None:
    from importlib.metadata import version as pkg_version

    console = Console()
    try:
        ver = pkg_version("octop")
    except Exception:
        ver = "unknown"
    console.print(f"  [bold green]Octop[/] [dim]v{ver}[/] — interactive chat")
    console.print(f"  [dim]Agent: {agent_id}  Model: {model or 'default'}[/]")
    console.print(f"  [dim]Session: {session_key}[/]", end="")
    if thread_id:
        console.print(f"  Thread: {thread_id[:12]}…[/]")
    else:
        console.print()
    console.print("  [dim]Type /exit or Ctrl+C to quit; /help for slash commands[/]")
    console.print()


def render_markdown_reply(
    text: str,
    *,
    theme: ChatTheme | None = None,
    console: Console | None = None,
) -> None:
    theme = theme or ChatTheme()
    console = console or Console()
    md = Markdown(text.strip(), code_theme="monokai")
    with console.capture() as capture:
        console.print(md, highlight=False)
    lines = capture.get().rstrip("\n").split("\n")
    if not lines:
        return
    console.print(f"  [{theme.dot_ai}]●[/] {lines[0]}", highlight=False)
    for line in lines[1:]:
        console.print(f"    {line}", highlight=False)
