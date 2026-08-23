"""Platform slash commands (help, agents, cron, connectors, token)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness_agent.slash import SlashCommand, SlashSink

from octop.i18n.domains.slash import localized_rows, tr
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.slash.catalog import channel_origin
from octop.infra.gateway.slash.ctx import SlashCtx, ensure_thread_id, lang_of, resolve_user_agent
from octop.infra.gateway.slash.formatting import markdown_bullets, markdown_kv_block
from octop.infra.gateway.slash.help import format_help
from octop.infra.gateway.slash.types import GatewayHandler

if TYPE_CHECKING:
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher


async def cmd_help(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    specs = d.list_command_specs(origin=channel_origin(ctx.channel_type))
    await sink.text(format_help(specs, lang_of(ctx)))


async def cmd_token(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    tid = await ensure_thread_id(ctx)
    if ctx.usage_repo is None:
        await sink.text(tr("token.unavailable", lang))
        return
    totals = ctx.usage_repo.thread_totals(agent_id=ctx.agent_id, thread_id=tid)
    if totals["turns"] == 0:
        await sink.text(tr("token.empty", lang))
        return
    cache_hit = (
        round(totals["cache_read_tokens"] / totals["input_tokens"] * 100)
        if totals["input_tokens"]
        else 0
    )
    await sink.text(
        markdown_kv_block(
            tr("token.title", lang, short=tid[-6:]),
            localized_rows(
                [
                    ("input", f"{totals['input_tokens']:,}"),
                    ("cache_read", f"{totals['cache_read_tokens']:,}"),
                    ("cache_hit", f"{cache_hit}%"),
                    ("output", f"{totals['output_tokens']:,}"),
                    ("total", f"{totals['total_tokens']:,}"),
                    ("turns", str(totals["turns"])),
                ],
                lang,
            ),
        )
    )


async def cmd_cron(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    if ctx.cron_manager is None:
        await sink.text(tr("cron.unavailable", lang))
        return
    sub = (cmd.args.strip().lower() or "list").split()[0]
    if sub != "list":
        await sink.text(tr("cron.usage", lang))
        return
    jobs = ctx.cron_manager.list_by_agent(ctx.agent_id, include_disabled=False)
    if not jobs:
        await sink.text(tr("cron.empty", lang))
        return
    bullets = [f"`{j.cron_id[-6:]}` {j.trigger} — {j.prompt[:40]}" for j in jobs[:15]]
    await sink.text(markdown_bullets(tr("cron.title", lang), bullets))


async def cmd_agent(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    args = cmd.args.strip()
    if not args:
        await sink.text(tr("agent.usage", lang))
        return
    parts = args.split(maxsplit=1)
    sub = parts[0].lower()
    if sub == "list":
        if ctx.agent_manager is None:
            await sink.text(tr("agent.unavailable", lang))
            return
        rows = ctx.agent_manager.list_agents(ctx.user_id)
        if not rows:
            await sink.text(tr("agent.empty", lang))
            return
        bullets: list[str] = []
        for row in rows:
            marker = tr("agent.current", lang) if row.agent_id == ctx.agent_id else ""
            bullets.append(f"`{row.agent_id[-6:]}` **{row.name}**{marker}")
        await sink.text(markdown_bullets(tr("agent.list_title", lang), bullets))
        return
    if sub == "switch":
        target = parts[1].strip() if len(parts) > 1 else ""
        if not target:
            await sink.text(tr("agent.switch_usage", lang))
            return
        target_row = resolve_user_agent(ctx, target)
        if target_row is None:
            await sink.text(tr("agent.not_found", lang, name=target))
            return
        if hasattr(sink, "action"):
            await sink.action("switch_agent", agent_id=target_row.agent_id)
        await sink.text(tr("agent.switched", lang, name=target_row.name))
        return
    target_row = resolve_user_agent(ctx, args)
    if target_row is None:
        await sink.text(tr("agent.not_found", lang, name=args))
        return
    if hasattr(sink, "action"):
        await sink.action("switch_agent", agent_id=target_row.agent_id)
    await sink.text(tr("agent.switched", lang, name=target_row.name))


async def cmd_connectors(
    d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink
) -> None:
    lang = lang_of(ctx)
    sub = (cmd.args.strip().lower() or "list").split()[0]
    if sub != "list":
        await sink.text(tr("connectors.usage", lang))
        return
    if ctx.connector_repo is None:
        await sink.text(tr("connectors.unavailable", lang))
        return
    from octop.infra.connectors.service import list_user_connector_instances

    rows = list_user_connector_instances(
        ctx.connector_repo,
        ctx.user_id,
        active_only=True,
        with_credentials=True,
    )
    if not rows:
        await sink.text(tr("connectors.empty", lang))
        return
    bullets = [f"`{r.mcp_server_name}` **{r.display_name}** ({r.kind})" for r in rows[:20]]
    await sink.text(markdown_bullets(tr("connectors.title", lang), bullets))


async def cmd_exit(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    raise OctopError(ErrorCode.SLASH_BAD_ARGS, "/exit handled at CLI level")


PLATFORM_HANDLERS: dict[str, GatewayHandler] = {
    "help": cmd_help,
    "token": cmd_token,
    "cron": cmd_cron,
    "agent": cmd_agent,
    "connectors": cmd_connectors,
    "exit": cmd_exit,
}
