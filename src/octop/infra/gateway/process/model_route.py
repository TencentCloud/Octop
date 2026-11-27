"""Resolve the same conversation model for a normal turn and manual compaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from octop.infra.users.preferences import get_preferred_model_from_json

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.db.repos.agents import AgentRepo
    from octop.infra.db.repos.users import UserRepo
    from octop.infra.gateway.threads import ThreadRegistry


@dataclass(frozen=True)
class ResolvedModelRoute:
    model_ref: str | None
    automatic: bool


def model_ref_from_meta(
    thread_model: str | None,
    meta: dict[str, Any] | None,
    sticky_model: str | None = None,
) -> str | None:
    meta_model = (meta or {}).get("model")
    # Explicit composer choice wins, followed by its persisted conversation
    # value. The legacy /model override remains supported at lower priority.
    model_ref = meta_model or sticky_model or thread_model
    if isinstance(model_ref, str):
        stripped = model_ref.strip()
        return stripped or None
    return None


def resolve_conversation_route(
    manager: AgentManager,
    threads: ThreadRegistry,
    agent_repo: AgentRepo | None,
    user_repo: UserRepo | None,
    agent_id: str,
    thread_id: str,
    meta: dict[str, Any] | None,
    *,
    user_id: int,
    needs_multimodal: bool,
) -> ResolvedModelRoute:
    providers = manager.providers
    thread_model = manager.get_thread_model(agent_id, thread_id)
    thread_row = threads.get_thread(thread_id)
    model_ref = model_ref_from_meta(
        thread_model,
        meta,
        thread_row.model_ref if thread_row is not None else None,
    )
    automatic = False
    if model_ref and not providers.is_model_ref_usable(model_ref):
        model_ref = None
    if model_ref and not manager.model_ref_allowed_for_user(user_id, model_ref):
        model_ref = None
    if not model_ref:
        row = agent_repo.get(agent_id) if agent_repo else None
        if row is not None:
            model_ref = providers.resolve_explicit_default_model(
                row,
                manager.get_config(agent_id),
            )
            if model_ref and not manager.model_ref_allowed_for_user(
                user_id,
                model_ref,
            ):
                model_ref = None
    if not model_ref:
        user_row = user_repo.get(user_id) if user_repo else None
        preferred = get_preferred_model_from_json(
            user_row.preferences_json if user_row is not None else None
        )
        if (
            preferred
            and manager.is_auto_route_model_available(preferred)
            and manager.model_ref_allowed_for_user(user_id, preferred)
        ):
            model_ref = preferred
            automatic = True
    if not model_ref:
        fallback = manager.resolve_fallback_model_ref()
        candidate = fallback.strip() if isinstance(fallback, str) and fallback.strip() else None
        if candidate and manager.model_ref_allowed_for_user(user_id, candidate):
            model_ref = candidate
            automatic = True
    if not model_ref:
        return ResolvedModelRoute(None, automatic=True)
    resolved = providers.resolve_model_for_multimodal_turn(
        model_ref,
        needs_multimodal=needs_multimodal,
    )
    if resolved != model_ref:
        automatic = True
    return ResolvedModelRoute(resolved, automatic=automatic)
