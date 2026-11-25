"""Knowledge bases and connectors for one expert turn.

Chat, cron, and team dispatch all resolve a turn through here so the
selection rules stay in one place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedTurnMcp:
    """Viewer names were requested; harness names are what the model sees."""

    requested: list[str]
    harness: list[str]
    shown: list[str]
    failed: list[str]


def attach_turn_knowledge(
    request: dict[str, Any],
    *,
    knowledge_repo: Any,
    user_id: int,
    is_admin: bool,
    explicit_ids: list[str] | None,
    extra_ids: list[str] | None,
    locale: str,
) -> list[str]:
    """Stamp this turn's visible knowledge bases onto ``request``."""
    from octop.infra.knowledge.default_open import stamp_turn_knowledge_config

    bases = knowledge_repo.list_all() if is_admin else knowledge_repo.list_visible(user_id)
    if not isinstance(bases, list):
        return []
    return stamp_turn_knowledge_config(
        request,
        visible_bases=bases,
        explicit_ids=explicit_ids,
        owner_user_id=user_id,
        extra_ids=extra_ids,
        is_admin=is_admin,
        locale=locale,
    )


async def resolve_turn_mcp(
    agent_manager: Any,
    *,
    agent_id: str,
    user_id: int,
    explicit: list[str] | None,
    apply_defaults: bool | None = None,
) -> ResolvedTurnMcp | None:
    """Merge expert picks with default-open connectors and load their tools.

    ``failed`` lists servers that did not load. Callers that abort on any
    failure ignore ``harness`` when it is non-empty. Team dispatch keeps the
    names that loaded.
    """
    from octop.infra.agents.teams.service import is_team_agent

    row = agent_manager.get_row(agent_id)
    if is_team_agent(row):
        return None
    owner_raw = getattr(row, "user_id", None) if row is not None else None
    owner_id = owner_raw if isinstance(owner_raw, int) else None
    extra_defaults = agent_manager.default_mcp_servers(agent_id)
    merged = agent_manager.merge_turn_mcp_servers(
        user_id,
        explicit,
        apply_defaults=apply_defaults,
        extra_defaults=extra_defaults,
        agent_owner_id=owner_id,
    )
    if not isinstance(merged, list) or not merged:
        return None
    requested = [str(name) for name in merged if str(name).strip()]
    if not requested:
        return None
    harness = list(requested)
    shown = list(requested)
    if owner_id is not None and owner_id != user_id:
        harness = list(agent_manager.align_mcp_names_to_harness(owner_id, user_id, requested))
        shown = list(agent_manager.mcp_names_for_chips(owner_id, user_id, requested, harness))
    from octop.infra.agents.managed import is_managed_agent

    # Managed experts receive these servers on the ACP session. Loading the
    # same tools into the in-process graph is not how that turn runs.
    if is_managed_agent(row):
        return ResolvedTurnMcp(
            requested=requested,
            harness=harness,
            shown=shown,
            failed=[],
        )
    # Native turn scopes use the same catalog names for loading and execution.
    failed = await agent_manager.prepare_chat_mcp(
        agent_id,
        shown,
        connector_user_id=user_id,
    )
    missing = [str(name) for name in failed] if isinstance(failed, list) else list(shown)
    return ResolvedTurnMcp(
        requested=requested,
        harness=shown,
        shown=shown,
        failed=missing,
    )


def harness_names_for_ready(resolved: ResolvedTurnMcp) -> list[str]:
    """Harness names for the servers that actually loaded."""
    failed = set(resolved.failed)
    return [name for name in resolved.harness if name not in failed]
