"""Composite slash commands (gateway + harness runtime data)."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from harness_agent.slash import SlashCommand, SlashSink, thread_message_count

from octop.i18n.domains.agents import agent_error_message
from octop.i18n.domains.slash import localized_rows, tr
from octop.infra.gateway.slash.ctx import SlashCtx, ensure_thread_id, lang_of
from octop.infra.gateway.slash.formatting import (
    format_duration,
    markdown_kv_block,
    server_uptime_label,
)
from octop.infra.gateway.slash.types import GatewayHandler
from octop.infra.utils.locale import Locale, normalize_locale

if TYPE_CHECKING:
    from octop.infra.db.repos.users import UserRepo
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher

logger = logging.getLogger(__name__)


def _format_slash_user(
    user_repo: UserRepo | None,
    user_id: int | None,
    lang: str,
    *,
    shared_label: str,
) -> str:
    if user_id is None:
        return shared_label
    if user_repo is None:
        return str(user_id)
    row = user_repo.get(user_id)
    if row is None:
        return str(user_id)
    locale: Locale = normalize_locale(lang)
    return tr("status.user_fmt", locale, username=row.username, user_id=user_id)


def _resolve_agent_row(ctx: SlashCtx) -> Any:
    if ctx.agent_manager is not None:
        return ctx.agent_manager.get_row(ctx.agent_id)
    if ctx.agent_repo is not None:
        return ctx.agent_repo.get(ctx.agent_id)
    return None


async def cmd_compact(
    d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink
) -> None:
    """Force summarization + history offload on the current thread.

    This mirrors deepagents ``SummarizationMiddleware`` (summary message +
    ``conversation_history`` offload via ``_summarization_event``). Unlike
    ``/new``, it does **not** create a fresh thread.
    """
    from pathlib import Path  # noqa: PLC0415

    lang = lang_of(ctx)
    tid = ctx.thread_registry.get_bound_thread_id(ctx.session_key)
    if not tid:
        await sink.text(tr("compact.no_thread", lang))
        return
    if ctx.agent_manager is None:
        await sink.text(tr("compact.unavailable", lang))
        return

    try:
        harness = ctx.agent_manager.get_agent(ctx.agent_id)
    except Exception:
        logger.exception("compact: get_agent failed agent_id=%s", ctx.agent_id)
        await sink.text(tr("compact.unavailable", lang))
        return

    compact = getattr(harness, "acompact_conversation", None)
    if compact is None:
        await sink.text(tr("compact.unavailable", lang))
        return

    model_override = d.get_thread_model_override(ctx, tid)
    try:
        result = await compact(tid, model=model_override)
    except Exception:
        logger.exception("compact: acompact_conversation failed thread=%s", tid)
        await sink.text(tr("compact.failed", lang))
        return

    reason = getattr(result, "reason", "") or ""
    if not getattr(result, "ok", False):
        err = getattr(result, "error", None)
        if reason == "nothing_to_compact":
            await sink.text(tr("compact.nothing", lang, short=tid[-6:]))
        elif reason == "unavailable":
            logger.warning("compact unavailable thread=%s err=%s", tid, err)
            await sink.text(tr("compact.unavailable", lang))
        else:
            logger.warning("compact failed thread=%s reason=%s err=%s", tid, reason, err)
            await sink.text(tr("compact.failed", lang))
        return

    count = int(getattr(result, "summarized_count", 0) or 0)
    raw_path = getattr(result, "file_path", None) or ""
    if raw_path:
        p = Path(str(raw_path))
        # Prefer short workspace-relative display over absolute host paths.
        short_path = f"conversation_history/{p.name}" if p.name else str(raw_path)
        await sink.text(
            tr("compact.done_offload", lang, count=count, short=tid[-6:], path=short_path)
        )
    else:
        await sink.text(tr("compact.done", lang, count=count, short=tid[-6:]))


async def cmd_history(
    d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink
) -> None:
    lang = lang_of(ctx)
    tid = await ensure_thread_id(ctx)
    row = ctx.thread_registry.get_thread(tid)
    msg_count = 0
    if ctx.agent_manager is not None:
        try:
            harness = ctx.agent_manager.get_agent(ctx.agent_id)
            msg_count = await thread_message_count(harness, tid)
        except Exception:
            msg_count = 0
    title = row.title if row else None
    rows: list[tuple[str, str]] = [
        ("thread", tid[-6:]),
        ("messages", str(msg_count)),
        ("title", title or tr("untitled", lang)),
    ]
    if row is not None:
        rows.append(("pinned", tr("yes", lang) if row.pinned else tr("no", lang)))
        if row.last_active:
            rows.append(("last_active", str(row.last_active)))
    override = d.get_thread_model_override(ctx, tid)
    if override:
        rows.append(("model_override", override))
    await sink.text(markdown_kv_block(tr("history.title", lang), localized_rows(rows, lang)))


async def cmd_status(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    tid = await ensure_thread_id(ctx)
    row = ctx.thread_registry.get_thread(tid)

    from octop.i18n.domains.agents import agent_state_label  # noqa: PLC0415

    agent_row = _resolve_agent_row(ctx)
    agent_state = agent_state_label(None, lang)
    default_model: str | None = None
    agent_name: str | None = None
    if agent_row is not None:
        agent_state = agent_state_label(agent_row.last_state, lang)
        default_model = agent_row.default_model
        agent_name = agent_row.name

    override = d.get_thread_model_override(ctx, tid)
    if override:
        model_line = tr("status.model_override", lang, model=override)
    elif default_model:
        model_line = tr("status.model_default", lang, model=default_model)
    else:
        model_line = tr("status.model_auto", lang)

    msg_count = 0
    if ctx.agent_manager is not None:
        try:
            harness = ctx.agent_manager.get_agent(ctx.agent_id)
            msg_count = await thread_message_count(harness, tid)
        except Exception:
            msg_count = 0

    token_line = tr("status.tokens_none", lang)
    if ctx.usage_repo is not None:
        totals = ctx.usage_repo.thread_totals(agent_id=ctx.agent_id, thread_id=tid)
        if totals["turns"] > 0:
            token_line = tr(
                "status.tokens_summary",
                lang,
                total=totals["total_tokens"],
                input=totals["input_tokens"],
                output=totals["output_tokens"],
                turns=totals["turns"],
            )

    session_age = ""
    if row is not None and row.created_at:
        session_age = format_duration(int(time.time()) - int(row.created_at))

    session_key_display = (
        f"…{ctx.session_key[-24:]}" if len(ctx.session_key) > 24 else ctx.session_key
    )
    thread_label = f"`{tid[-6:]}` — {row.title if row and row.title else tr('untitled', lang)}"

    workspace_line = tr("unknown", lang)
    if ctx.paths is not None:
        workspace_line = str(ctx.paths.agent_workspace(ctx.agent_id))

    chat_user_line = _format_slash_user(
        ctx.user_repo,
        ctx.user_id if ctx.user_id > 0 else None,
        lang,
        shared_label="—",
    )
    owner_line = _format_slash_user(
        ctx.user_repo,
        agent_row.user_id if agent_row is not None else None,
        lang,
        shared_label=tr("status.owner_shared", lang),
    )

    rows: list[tuple[str, str]] = [
        ("octop", ctx.octop_version or tr("unknown", lang)),
        ("uptime", server_uptime_label(ctx.server_started_at)),
        ("agent_id", ctx.agent_id),
        ("agent", f"{agent_name or ctx.agent_id[-6:]} ({agent_state})"),
        ("owner", owner_line),
        ("chat_user", chat_user_line),
        ("workspace", workspace_line),
        ("model", model_line),
        ("thread", thread_label),
        ("session", f"`{session_key_display}`"),
        ("channel", ctx.channel_type),
        ("context", tr("status.context", lang, count=msg_count)),
        ("tokens", token_line),
    ]
    if agent_row is not None and agent_row.template_name:
        rows.insert(7, ("template", agent_row.template_name))
    if session_age:
        rows.append(("thread_age", session_age))
    if row is not None:
        rows.append(("pinned", tr("yes", lang) if row.pinned else tr("no", lang)))
    if ctx.gateway_channels:
        kinds = ", ".join(c.get("kind", "?") for c in ctx.gateway_channels[:5])
        rows.append(
            (
                "im_channels",
                tr("status.im_channels", lang, count=len(ctx.gateway_channels), kinds=kinds),
            )
        )
    if ctx.cron_manager is not None:
        cron_count = len(ctx.cron_manager.list_by_agent(ctx.agent_id, include_disabled=False))
        rows.append(("cron_jobs", str(cron_count)))
    if agent_row is not None and agent_row.last_error:
        rows.append(
            (
                "last_error",
                agent_error_message(agent_row.last_error, lang)[:120],
            )
        )

    await sink.text(markdown_kv_block(tr("status.title", lang), localized_rows(rows, lang)))


async def cmd_model(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    tid = await ensure_thread_id(ctx)
    name = cmd.args.strip()
    if not name:
        override = d.get_thread_model_override(ctx, tid)
        default_model: str | None = None
        if ctx.agent_manager is not None:
            row = ctx.agent_manager.get_row(ctx.agent_id)
            if row is not None:
                default_model = row.default_model
        elif ctx.agent_repo is not None:
            row = ctx.agent_repo.get(ctx.agent_id)
            if row is not None:
                default_model = row.default_model
        if override:
            await sink.text(tr("model.override", lang, model=override))
        elif default_model:
            await sink.text(tr("model.current_default", lang, model=default_model))
        else:
            await sink.text(tr("model.usage", lang))
        return
    if name.lower() == "reset":
        d.clear_thread_model_override(ctx, tid)
        if hasattr(sink, "action"):
            await sink.action("clear_model")
        await sink.text(tr("model.cleared", lang))
        return
    d.set_thread_model_override(ctx, tid, name)
    if hasattr(sink, "action"):
        await sink.action("set_model", model=name)
    await sink.text(tr("model.set", lang, model=name))


COMPOSITE_HANDLERS: dict[str, GatewayHandler] = {
    "compact": cmd_compact,
    "history": cmd_history,
    "status": cmd_status,
    "model": cmd_model,
    "models": cmd_model,
}
