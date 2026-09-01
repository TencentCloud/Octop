"""Bootstrap a first default agent (general-assistant) for a user.

Used by the setup wizard (pinned ``agent_id=main``) and by invite redeem
(auto-allocated agent id) so every new account starts with the same expert.
"""

from __future__ import annotations

import logging
from typing import Any

from octop.infra.agents.experts.catalog import ExpertCatalog, build_create_spec_from_expert
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.host_dirs import host_home_dir, host_path_text
from octop.infra.utils.locale import normalize_locale

logger = logging.getLogger(__name__)

DEFAULT_EXPERT_ID = "general-assistant"
SETUP_DEFAULT_AGENT_ID = "main"


def default_home_local_backend() -> dict[str, Any]:
    """Same local backend as the dashboard create-from-expert default (home-scoped)."""
    return {
        "type": "local_shell",
        "root_dir": host_path_text(host_home_dir()),
        "virtual_mode": True,
    }


async def bootstrap_default_agent(
    registry: Any,
    catalog: ExpertCatalog | None,
    *,
    user_id: int,
    locale: str = "zh",
    agent_id: str | None = None,
) -> Any | None:
    """Create ``general-assistant`` for *user_id* when they have no agents yet.

    Returns the created agent row, or ``None`` when skipped (user already has
    agents, or ``main`` already exists when *agent_id* is ``main``).
    """
    if agent_id == SETUP_DEFAULT_AGENT_ID and registry.get_row(SETUP_DEFAULT_AGENT_ID) is not None:
        return None
    if registry.list_agents(user_id):
        return None
    if catalog is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "expert catalog not available")
    expert = catalog.get(DEFAULT_EXPERT_ID)
    if expert is None:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            f"{DEFAULT_EXPERT_ID} expert template missing",
        )
    loc = normalize_locale(locale)
    spec = build_create_spec_from_expert(
        expert_id=DEFAULT_EXPERT_ID,
        expert=expert,
        user_id=user_id,
        agent_id=agent_id,
        locale=loc,
        config_extra={"backend": default_home_local_backend()},
    )
    return await registry.create(spec, defer_bootstrap=True)


async def try_bootstrap_default_agent(
    server: Any,
    *,
    user_id: int,
    locale: str = "zh",
    agent_id: str | None = None,
) -> None:
    """Best-effort wrapper used by HTTP adapters (setup / invite)."""
    if server.app_runtime is None:
        logger.warning("skip default agent bootstrap: app_runtime not ready")
        return
    try:
        await bootstrap_default_agent(
            server.app_runtime.agent_registry,
            server.expert_catalog,
            user_id=user_id,
            locale=locale,
            agent_id=agent_id,
        )
    except Exception as exc:  # pragma: no cover - logged; user creation should still succeed
        logger.warning("could not auto-create default agent for user %s: %s", user_id, exc)
