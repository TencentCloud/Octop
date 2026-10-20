"""Runtime slash command handlers: stop, model, skills."""

from __future__ import annotations

from typing import TYPE_CHECKING

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.slash.core import (
    RuntimeHandler,
    markdown_bullets,
    normalize_locale,
    tr,
)

if TYPE_CHECKING:
    from octop_harness.slash.core import (
        RuntimeSlashCtx,
        RuntimeSlashDispatcher,
        SlashCommand,
        SlashSink,
    )


async def handle_stop(
    _d: RuntimeSlashDispatcher,
    _cmd: SlashCommand,
    ctx: RuntimeSlashCtx,
    sink: SlashSink,
) -> None:
    lang = normalize_locale(ctx.locale)
    tid = ctx.thread_id
    if tid and ctx.cancel_stream is not None:
        ctx.cancel_stream(ctx.agent_id, tid)
        await sink.text(tr("stop.done", lang))
        return
    await sink.text(tr("stop.empty", lang))


async def handle_model(
    _d: RuntimeSlashDispatcher,
    cmd: SlashCommand,
    ctx: RuntimeSlashCtx,
    sink: SlashSink,
) -> None:
    lang = normalize_locale(ctx.locale)
    tid = ctx.thread_id
    if not tid:
        await sink.text(tr("model.usage", lang))
        return
    name = cmd.args.strip()
    if not name:
        override = ctx.get_thread_model(ctx.agent_id, tid) if ctx.get_thread_model else None
        if override:
            await sink.text(tr("model.override", lang, model=override))
        elif ctx.default_model:
            await sink.text(tr("model.current_default", lang, model=ctx.default_model))
        else:
            await sink.text(tr("model.usage", lang))
        return
    if name.lower() == "reset":
        if ctx.clear_thread_model is not None:
            ctx.clear_thread_model(ctx.agent_id, tid)
        await sink.text(tr("model.cleared", lang))
        return
    if ctx.set_thread_model is not None:
        ctx.set_thread_model(ctx.agent_id, tid, name)
    await sink.text(tr("model.set", lang, model=name))


async def handle_skills(
    _d: RuntimeSlashDispatcher,
    cmd: SlashCommand,
    ctx: RuntimeSlashCtx,
    sink: SlashSink,
) -> None:
    lang = normalize_locale(ctx.locale)
    sub = (cmd.args.strip().lower() or "list").split()[0]
    if sub != "list":
        await sink.text(tr("skills.usage", lang))
        return
    if ctx.list_skills is None:
        await sink.text(tr("skills.unavailable", lang))
        return
    try:
        rows = await ctx.list_skills()
    except DEFENSIVE_OP_ERRORS:
        await sink.text(tr("skills.unavailable", lang))
        return
    if not rows:
        await sink.text(tr("skills.empty", lang))
        return
    bullets: list[str] = []
    for row in rows[:20]:
        state = tr("skills.enabled", lang) if row.get("enabled") else tr("skills.disabled", lang)
        desc = str(row.get("description") or "")[:50]
        name = str(row.get("name") or "")
        emoji = str(row.get("emoji") or "").strip()
        label = f"{emoji} {name}".strip() if emoji else name
        line = f"**{label}** ({state})"
        if desc:
            line += f" — {desc}"
        bullets.append(line)
    await sink.text(markdown_bullets(tr("skills.title", lang), bullets))


RUNTIME_HANDLERS: dict[str, RuntimeHandler] = {
    "stop": handle_stop,
    "cancel": handle_stop,
    "model": handle_model,
    "models": handle_model,
    "skills": handle_skills,
}
