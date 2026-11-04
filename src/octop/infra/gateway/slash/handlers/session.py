"""Session / thread slash commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from octop_harness.slash import SlashCommand, SlashSink

from octop.i18n import error_message
from octop.i18n.domains.slash import tr
from octop.infra.agents.threads.rewind import rewind_thread
from octop.infra.db.repos.threads import clip_thread_title
from octop.infra.errors import ErrorCode, OctopError
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
    rows = ctx.thread_registry.list_threads(agent_id=ctx.agent_id, user_id=ctx.user_id, limit=10)
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
    target = find_thread_by_short(ctx.thread_registry, ctx.agent_id, ctx.user_id, short)
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
        target = find_thread_by_short(ctx.thread_registry, ctx.agent_id, ctx.user_id, short)
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
    target = find_thread_by_short(ctx.thread_registry, ctx.agent_id, ctx.user_id, short)
    if target is None:
        await sink.text(tr("delete.not_found", lang, short=short))
        return
    if active and target.thread_id == active:
        await sink.text(tr("delete.active", lang))
        return
    hub = ctx.ws_hub
    if hub is not None and hub.is_turn_active(target.thread_id):
        await sink.text(error_message("THREAD_TURN_ACTIVE", lang))
        return
    if ctx.agent_manager is None:
        await sink.text(tr("delete.failed", lang))
        return
    try:
        await ctx.agent_manager.delete_thread_checkpoint(ctx.agent_id, target.thread_id)
    except OctopError:
        await sink.text(tr("delete.failed", lang))
        return
    ctx.thread_registry.delete_thread(target.thread_id)
    await sink.text(tr("delete.done", lang, short=target.thread_id[-6:]))


_UNDO_SKIP = frozenset({"now", "--yes", "-y"})
_UNDO_ERRORS = {
    ErrorCode.UNDO_EMPTY: "undo.empty",
    ErrorCode.UNDO_NOT_FOUND: "undo.not_found",
    ErrorCode.UNDO_CONFLICT: "undo.conflict",
    ErrorCode.UNDO_FAILED: "undo.failed",
    ErrorCode.AGENT_NOT_RUNNING: "undo.unavailable",
    ErrorCode.SLASH_BAD_ARGS: "undo.usage",
}


def _parse_undo_turns(args: str) -> int | None:
    parts = [
        part
        for part in args.split()
        if part not in _UNDO_SKIP and not (part.startswith("[") and part.endswith("]"))
    ]
    if not parts:
        return 1
    try:
        count = int(parts[0])
    except ValueError:
        return None
    if count < 1:
        return None
    return count


async def cmd_undo(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    count = _parse_undo_turns(cmd.args)
    if count is None:
        await sink.text(tr("undo.usage", lang))
        return
    tid = ctx.thread_registry.get_bound_thread_id(ctx.session_key)
    if not tid:
        await sink.text(tr("undo.empty", lang))
        return
    # The dashboard marks this slash request active before the handler runs.
    # That flag is the command itself, not a reply still streaming.
    hitl = ctx.hitl
    if hitl is not None and tid in hitl.store.pending_thread_ids(
        agent_id=ctx.agent_id, user_id=ctx.user_id
    ):
        await sink.text(tr("undo.busy", lang))
        return
    if ctx.agent_manager is None:
        await sink.text(tr("undo.unavailable", lang))
        return
    try:
        harness = ctx.agent_manager.get_agent(ctx.agent_id)
    except OctopError:
        await sink.text(tr("undo.unavailable", lang))
        return
    try:
        outcome = await rewind_thread(
            harness=harness,
            thread_id=tid,
            turns=count,
            thread_message_repo=ctx.thread_message_repo,
            history_archive=ctx.history_archive,
            hitl=ctx.hitl,
            agent_id=ctx.agent_id,
            user_id=ctx.user_id,
        )
    except OctopError as exc:
        key = _UNDO_ERRORS.get(exc.code, "undo.failed")
        await sink.text(tr(key, lang))
        return
    preview = outcome.prefill_text
    if len(preview) > 60:
        preview = preview[:60] + "..."
    await sink.text(tr("undo.done", lang, count=outcome.turns_undone, preview=preview or "…"))
    if hasattr(sink, "action"):
        await sink.action(
            "undo",
            prefill=outcome.prefill_text,
            thread_id=tid,
            message_id=outcome.cut_message_id,
        )


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
    "undo": cmd_undo,
    "pin": cmd_pin,
    "unpin": cmd_unpin,
}
