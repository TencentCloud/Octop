"""Session / thread slash commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness_agent.slash import SlashCommand, SlashSink

from octop.i18n.domains.slash import tr
from octop.infra.db.repos.threads import clip_thread_title
from octop.infra.gateway.slash.ctx import (
    SlashCtx,
    chat_type,
    ensure_thread_id,
    find_thread_by_short,
    lang_of,
    subject_id,
)
from octop.infra.gateway.slash.formatting import markdown_bullets
from octop.infra.gateway.slash.types import GatewayHandler

if TYPE_CHECKING:
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher


async def cmd_new(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    new_tid = await ctx.thread_registry.reset(
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
        channel_subject_id=subject_id(ctx),
        channel_chat_type=chat_type(ctx),
    )
    if cmd.args:
        ctx.thread_registry.set_title_if_null(new_tid, cmd.args)
    lang = lang_of(ctx)
    if hasattr(sink, "action"):
        await sink.action("new_chat", thread_id=new_tid)
    await sink.text(tr("new.started", lang, short=new_tid[-6:]))


async def cmd_list(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    rows = ctx.thread_registry.list_threads(agent_id=ctx.agent_id, limit=10)
    if not rows:
        await sink.text(tr("list.empty", lang))
        return
    if cmd.name == "sessions":
        header = tr("list.title.sessions", lang)
    elif cmd.name == "topics":
        header = tr("list.title.topics", lang)
    else:
        header = tr("list.title.recent", lang)
    bullets: list[str] = []
    for r in rows:
        title = r.title or tr("untitled", lang)
        pin = " 📌" if r.pinned else ""
        bullets.append(f"`{r.thread_id[-6:]}` {title}{pin}")
    await sink.text(markdown_bullets(header, bullets))


async def cmd_switch(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    short = cmd.args.strip()
    if not short:
        await sink.text(tr("switch.usage", lang))
        return
    target = find_thread_by_short(ctx.thread_registry, ctx.agent_id, short)
    if target is None:
        await sink.text(tr("switch.not_found", lang, short=short))
        return
    await ctx.thread_registry.rebind(
        session_key=ctx.session_key, thread_id=target.thread_id, agent_id=ctx.agent_id
    )
    if hasattr(sink, "action"):
        await sink.action("rebind_thread", thread_id=target.thread_id)
    await sink.text(tr("switch.done", lang, short=target.thread_id[-6:]))


async def cmd_resume(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    short = cmd.args.strip()
    if short:
        target = find_thread_by_short(ctx.thread_registry, ctx.agent_id, short)
        if target is None:
            await sink.text(tr("switch.not_found", lang, short=short))
            return
        await ctx.thread_registry.rebind(
            session_key=ctx.session_key, thread_id=target.thread_id, agent_id=ctx.agent_id
        )
        if hasattr(sink, "action"):
            await sink.action("rebind_thread", thread_id=target.thread_id)
        await sink.text(tr("resume.done", lang, short=target.thread_id[-6:]))
        return
    current = ctx.thread_registry.get_bound_thread_id(ctx.session_key)
    rows = ctx.thread_registry.list_threads_for_session(session_key=ctx.session_key, limit=50)
    if len(rows) < 2:
        await sink.text(tr("resume.empty", lang))
        return
    target = rows[1] if rows[0].thread_id == current else rows[0]
    if target.thread_id == current:
        await sink.text(tr("resume.empty", lang))
        return
    await ctx.thread_registry.rebind(
        session_key=ctx.session_key, thread_id=target.thread_id, agent_id=ctx.agent_id
    )
    if hasattr(sink, "action"):
        await sink.action("rebind_thread", thread_id=target.thread_id)
    await sink.text(tr("resume.done", lang, short=target.thread_id[-6:]))


async def cmd_title(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    title = cmd.args.strip()
    if not title:
        await sink.text(tr("title.usage", lang))
        return
    tid = await ensure_thread_id(ctx)
    ctx.thread_registry.update_title(tid, title)
    await sink.text(tr("title.done", lang, title=clip_thread_title(title)))


async def cmd_delete(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    short = cmd.args.strip()
    if not short:
        await sink.text(tr("delete.usage", lang))
        return
    active = ctx.thread_registry.get_bound_thread_id(ctx.session_key)
    target = find_thread_by_short(ctx.thread_registry, ctx.agent_id, short)
    if target is None:
        await sink.text(tr("delete.not_found", lang, short=short))
        return
    if active and target.thread_id == active:
        await sink.text(tr("delete.active", lang))
        return
    ctx.thread_registry.delete_thread(target.thread_id)
    await sink.text(tr("delete.done", lang, short=target.thread_id[-6:]))


async def cmd_pin(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    tid = await ensure_thread_id(ctx)
    ctx.thread_registry.set_pinned(tid, True)
    await sink.text(tr("pin.done", lang))


async def cmd_unpin(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    tid = await ensure_thread_id(ctx)
    ctx.thread_registry.set_pinned(tid, False)
    await sink.text(tr("unpin.done", lang))


SESSION_HANDLERS: dict[str, GatewayHandler] = {
    "new": cmd_new,
    "list": cmd_list,
    "switch": cmd_switch,
    "resume": cmd_resume,
    "title": cmd_title,
    "delete": cmd_delete,
    "pin": cmd_pin,
    "unpin": cmd_unpin,
}
