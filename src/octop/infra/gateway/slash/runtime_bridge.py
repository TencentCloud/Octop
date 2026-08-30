"""Bridge gateway SlashCtx to harness runtime slash context."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from harness_agent.slash import RuntimeSlashCtx, SlashCommand

from octop.infra.gateway.slash.ctx import SlashCtx, ensure_thread_id

if TYPE_CHECKING:
    pass


async def build_runtime_ctx(cmd: SlashCommand, ctx: SlashCtx) -> RuntimeSlashCtx:
    default_model: str | None = None
    if ctx.agent_manager is not None:
        row = ctx.agent_manager.get_row(ctx.agent_id)
        if row is not None:
            default_model = row.default_model
    elif ctx.agent_repo is not None:
        row = ctx.agent_repo.get(ctx.agent_id)
        if row is not None:
            default_model = row.default_model

    if cmd.name in ("stop", "cancel"):
        thread_id = ctx.thread_registry.get_bound_thread_id(ctx.session_key)
    else:
        thread_id = await ensure_thread_id(ctx)
    cancel_stream = None
    list_skills = None
    _get_thread_model = None
    _set_thread_model = None
    _clear_thread_model = None
    if ctx.agent_manager is not None:
        am = ctx.agent_manager

        def _cancel(agent_id: str, tid: str) -> None:
            am.cancel_stream(agent_id, tid)

        cancel_stream = _cancel

        async def _list_skills() -> list[dict[str, Any]]:
            from octop.infra.utils.locale import normalize_locale

            return await am.list_skill_summaries(
                ctx.agent_id,
                locale=normalize_locale(ctx.locale),
            )

        list_skills = _list_skills

        def _get_thread_model(agent_id: str, tid: str) -> str | None:
            return am.get_thread_model(agent_id, tid)

        def _set_thread_model(agent_id: str, tid: str, model: str) -> None:
            am.set_thread_model(agent_id, tid, model)

        def _clear_thread_model(agent_id: str, tid: str) -> None:
            am.clear_thread_model(agent_id, tid)

    return RuntimeSlashCtx(
        agent_id=ctx.agent_id,
        thread_id=thread_id,
        locale=ctx.locale,
        default_model=default_model,
        cancel_stream=cancel_stream,
        list_skills=list_skills,
        get_thread_model=_get_thread_model,
        set_thread_model=_set_thread_model,
        clear_thread_model=_clear_thread_model,
    )
