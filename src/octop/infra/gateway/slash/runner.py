"""Shared slash command execution for IM processor and dashboard chat."""

from __future__ import annotations

from harness_agent.slash import BufferSink, SlashCommand, SlashSink

from octop.infra.gateway.slash.ctx import SlashCtx
from octop.infra.gateway.slash.dispatcher import SlashDispatcher
from octop.infra.gateway.slash.parser import parse_slash


async def try_handle_slash(
    text: str | None,
    *,
    dispatcher: SlashDispatcher,
    ctx: SlashCtx,
    sink: SlashSink | None = None,
) -> tuple[bool, list[str], list[dict[str, object]]]:
    """Parse *text* and dispatch if it is a slash command.

    Returns ``(handled, lines, actions)``. *handled* is False when *text* is not
    a known slash command (including unknown ``/foo`` names); True when a
    registered command ran.
    """
    cmd = parse_slash(text)
    if cmd is None:
        return False, [], []
    buf = sink if sink is not None else BufferSink()
    if sink is None:
        assert isinstance(buf, BufferSink)
    handled = await dispatcher.handle(cmd, ctx, buf)
    if isinstance(buf, BufferSink):
        return handled, buf.lines, buf.actions
    return handled, [], []


async def handle_slash_command(
    cmd: SlashCommand,
    *,
    dispatcher: SlashDispatcher,
    ctx: SlashCtx,
) -> list[str]:
    """Run a parsed command and return response lines."""
    sink = BufferSink()
    await dispatcher.handle(cmd, ctx, sink)
    return sink.lines
