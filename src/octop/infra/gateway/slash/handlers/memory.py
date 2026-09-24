"""Explicit memory maintenance commands for authenticated local chat users."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from harness_agent.slash import SlashCommand, SlashSink

from octop.i18n import tr as full_tr
from octop.i18n.domains.slash import tr
from octop.infra.gateway.slash.ctx import SlashCtx, lang_of
from octop.infra.gateway.threads import ThreadRegistry

if TYPE_CHECKING:
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher


def _status_line(state: dict[str, Any], locale: str) -> str:
    phase = state["phase"]
    if phase in {"queued", "skipped"}:
        label = full_tr(f"slash.memory.{phase}", locale)
    else:
        label = full_tr(f"memory_slim.{phase}", locale)
    line = f"[{state['agent_id']}] {label}"
    started = state.get("started_at")
    if started:
        end = state.get("updated_at", started) if phase in {"done", "failed"} else time.time()
        line += " " + full_tr("memory_slim.elapsed", locale, seconds=max(0, int(end - started)))
    if phase == "deduplicating" and "scanned" in state and "total" in state:
        line += " " + full_tr(
            "memory_slim.scanned", locale, scanned=state["scanned"], total=state["total"]
        )
    report = state.get("report")
    if phase == "done" and report:
        line += "\n" + full_tr(
            "memory_slim.result",
            locale,
            before=f"{report['before']['file_bytes'] / 1048576:.2f}",
            after=f"{report['after']['file_bytes'] / 1048576:.2f}",
            backup=Path(report["backup_path"]).name,
        )
    if phase == "failed":
        line += " " + full_tr("slash.memory.failure_hint", locale)
    return line


async def cmd_memory(d: SlashDispatcher, cmd: SlashCommand, ctx: SlashCtx, sink: SlashSink) -> None:
    lang = lang_of(ctx)
    # External IM user_id is the agent owner's persistence identity, NOT proof
    # that the sender is the owner. Do not authorize maintenance with that id.
    if not ThreadRegistry.is_virtual_channel(ctx.channel_type):
        await sink.text(tr("memory.trusted_chat", lang))
        return
    user = ctx.user_repo.get(ctx.user_id) if ctx.user_repo is not None else None
    if user is None or user.disabled or ctx.user_id <= 0:
        await sink.text(full_tr("memory_slim.forbidden", lang))
        return
    args = cmd.args.lower().split()
    is_slim = bool(args) and args[0] == "slim"
    flags = args[1:]
    valid_slim = is_slim and len(flags) == len(set(flags)) and set(flags) <= {"--all", "--confirm"}
    if not valid_slim and args != ["status"]:
        await sink.text(tr("memory.usage", lang))
        return
    if ctx.agent_manager is None:
        await sink.text(full_tr("memory_slim.not_ready", lang))
        return
    coordinator = ctx.agent_manager.memory_slim
    try:
        if args[0] == "slim":
            all_agents = "--all" in flags
            if "--confirm" not in flags:
                targets = coordinator.preview_chat(
                    ctx.agent_id, ctx.user_id, all_agents=all_agents, locale=lang
                )
                command = "/memory slim" + (" --all" if all_agents else "") + " --confirm"
                await sink.text(tr("memory.preview", lang, count=len(targets)))
                for target in targets:
                    await sink.text(f"- {target['name']} [{target['agent_id']}]")
                await sink.text(tr("memory.confirm_hint", lang, command=command))
                return
            count = coordinator.start_chat(
                ctx.agent_id,
                ctx.user_id,
                all_agents=all_agents,
                locale=lang,
            )
            await sink.text(tr("memory.accepted", lang, count=count))
            return
        snapshot = coordinator.chat_status(ctx.agent_id, ctx.user_id, locale=lang)
        states = snapshot["agents"]
        if not states:
            await sink.text(tr("memory.idle", lang))
            return
        await sink.text(
            tr(
                "memory.summary",
                lang,
                completed=sum(s["phase"] == "done" for s in states),
                total=len(states),
            )
        )
        for state in states:
            await sink.text(_status_line(state, lang))
    except ValueError as exc:
        await sink.text(str(exc))
