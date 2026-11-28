"""Model selection and user-facing diagnostics for manual compaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from octop.i18n.domains.slash import tr
from octop.infra.agents.settings.compaction import compaction_for_api
from octop.infra.gateway.process.model_route import resolve_conversation_route
from octop.infra.gateway.slash.ctx import SlashCtx, lang_of
from octop.infra.users.identity import User
from octop.infra.users.permissions import user_has_permission


@dataclass(frozen=True)
class CompactRoute:
    primary: str | None
    alternate: str | None
    scope: str
    skipped: str | None


def compact_route(ctx: SlashCtx, tid: str) -> CompactRoute:
    manager = ctx.agent_manager
    assert manager is not None
    expert = compaction_for_api(manager.get_config(ctx.agent_id)) or {}
    configured = expert.get("model")
    scope = "expert" if configured else "global"
    selected = configured if configured else manager.get_global_compaction_model()
    session = resolve_conversation_route(
        manager,
        ctx.thread_registry,
        ctx.agent_repo,
        ctx.user_repo,
        ctx.agent_id,
        tid,
        {"model": ctx.model_ref},
        user_id=ctx.user_id,
        needs_multimodal=False,
    ).model_ref
    candidates: list[str] = []
    skipped = None
    if selected and selected != "session":
        if not manager.model_ref_allowed_for_user(ctx.user_id, selected):
            skipped = tr("compact.restricted", lang_of(ctx))
        elif not manager.providers.is_model_ref_usable(selected):
            skipped = tr("compact.disabled", lang_of(ctx), model=selected)
        else:
            candidates.append(selected)
    if session and session not in candidates:
        candidates.append(session)
    if len(candidates) < 2:
        for candidate in manager.providers.list_auto_route_candidates(needs_multimodal=False):
            ref = candidate.ref
            if (
                ref not in candidates
                and manager.model_ref_allowed_for_user(ctx.user_id, ref)
                and manager.is_auto_route_model_available(ref)
            ):
                candidates.append(ref)
                if len(candidates) == 2:
                    break
    return CompactRoute(
        candidates[0] if candidates else None,
        candidates[1] if len(candidates) > 1 else None,
        scope,
        skipped,
    )


def settings_hint(ctx: SlashCtx, scope: str) -> str:
    lang = lang_of(ctx)
    user = ctx.user_repo.get(ctx.user_id) if ctx.user_repo else None
    agent = ctx.agent_repo.get(ctx.agent_id) if ctx.agent_repo else None
    is_admin = bool(user and user.role == "admin")
    can_global = user and user_has_permission(
        User(
            id=user.id,
            username=user.username,
            role=user.role,
            display_name=user.display_name,
            permissions=user.permissions,
        ),
        "providers",
    )
    if scope == "global" and can_global:
        label, target = "global_settings", "/admin/models?tab=chat#compact-model"
    elif agent and (agent.user_id == ctx.user_id or is_admin):
        label, target = "expert_settings", "/experts?compactModel=" + quote(ctx.agent_id, safe="")
    else:
        label, target = "session_settings", "#compact-session-model"
    text = tr("compact." + label, lang)
    return f"[{text}]({target})" if ctx.channel_type in {"ui", "dashboard"} else text


def compact_diagnostics(ctx: SlashCtx, route: CompactRoute, result: Any) -> list[str]:
    lang = lang_of(ctx)
    lines = [route.skipped] if route.skipped else []
    for failure in result.model_failures:
        reason = failure.reason
        if reason.startswith("http_"):
            code = reason.removeprefix("http_")
            key = {"401": "auth", "403": "auth", "402": "balance", "429": "rate"}.get(code)
            detail = f"HTTP {code}" + (f" ({tr('compact.' + key, lang)})" if key else "")
        else:
            detail = tr("compact." + reason, lang)
        lines.append(tr("compact.model_failed", lang, model=failure.model_ref, detail=detail))
    if result.failure_stage in ("offload", "checkpoint"):
        lines.append(tr("compact." + result.failure_stage, lang))
    if result.model_ref and (lines or not result.ok):
        lines.append(tr("compact.used", lang, model=result.model_ref))
    return lines
