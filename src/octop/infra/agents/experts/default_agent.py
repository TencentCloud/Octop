"""Bootstrap a first expert for a user.

Used by the setup wizard (pinned ``agent_id=main``), invite redeem, and
admin user creation. The template defaults to ``general-assistant`` and is
loaded from the expert market when it is not already in the local catalog.
A market miss does not fail the caller.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from octop.infra.agents.experts.catalog import ExpertCatalog, build_create_spec_from_expert
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.resource_policy import (
    POLICY_WORKSPACE_ROOT_DIR,
    effective_workspace_root_dir,
)
from octop.infra.utils.host_dirs import host_fs_tree_root
from octop.infra.utils.locale import normalize_locale

logger = logging.getLogger(__name__)

DEFAULT_EXPERT_ID = "general-assistant"
SETUP_DEFAULT_AGENT_ID = "main"


def default_home_local_backend(*, root_dir: str | None = None) -> dict[str, Any]:
    """Same local backend as the dashboard create-from-expert default.

    Defaults to host filesystem root; pass *root_dir* when a user
    ``workspace_root_dir`` policy applies.
    """
    resolved = (root_dir or "").strip() or host_fs_tree_root()
    return {
        "type": "local_shell",
        "root_dir": resolved,
        "virtual_mode": True,
    }


def user_policy_workspace_root(server: Any, user_id: int) -> str | None:
    """Effective ``workspace_root_dir`` policy for *user_id*, or ``None``."""
    return effective_workspace_root_dir(
        server.services.user_policy_repo.get(user_id, POLICY_WORKSPACE_ROOT_DIR)
    )


async def bootstrap_default_agent(
    registry: Any,
    catalog: ExpertCatalog | None,
    *,
    user_id: int,
    locale: str = "zh",
    agent_id: str | None = None,
    root_dir: str | None = None,
    expert_id: str | None = None,
) -> Any | None:
    """Create one expert for *user_id* when they have no agents yet.

    *expert_id* selects the catalog template (default ``general-assistant``).
    Returns the created agent row, or ``None`` when skipped (user already has
    agents, or ``main`` already exists when *agent_id* is ``main``).
    """
    template_id = (expert_id or "").strip() or DEFAULT_EXPERT_ID
    if agent_id == SETUP_DEFAULT_AGENT_ID and registry.get_row(SETUP_DEFAULT_AGENT_ID) is not None:
        return None
    if registry.list_agents(user_id):
        return None
    if catalog is None:
        raise OctopError(ErrorCode.DEFAULT_EXPERT_FAILED, "could not create default expert")
    expert = catalog.get(template_id)
    if expert is None:
        raise OctopError(
            ErrorCode.EXPERT_TEMPLATE_NOT_FOUND,
            "expert template not found",
        )
    loc = normalize_locale(locale)
    spec = build_create_spec_from_expert(
        expert_id=template_id,
        expert=expert,
        user_id=user_id,
        agent_id=agent_id,
        locale=loc,
        config_extra={"backend": default_home_local_backend(root_dir=root_dir)},
    )
    row = await registry.create(spec, defer_bootstrap=True)
    await _append_supplements(registry, row)
    return row


async def _append_supplements(registry: Any, row: Any) -> None:
    from octop.infra.agents.experts.supplements import append_supplements  # noqa: PLC0415

    agent_id = getattr(row, "agent_id", None)
    getter = getattr(registry, "workspace_for_agent", None)
    if agent_id is None or getter is None:
        return
    try:
        workspace = getter(agent_id)
    except Exception:
        logger.warning("skip supplements append: workspace unavailable for %s", agent_id)
        return
    if workspace is None:
        return
    await append_supplements(workspace)


async def materialize_market_expert(server: Any, template_id: str) -> bool:
    """Ensure *template_id* is in the catalog, pulling it from the expert market.

    Returns False when the catalog already lacks it and the market cannot
    supply a package. Callers keep going; this must not block user creation.
    """
    template_id = template_id.strip()
    if not template_id:
        return False
    catalog = getattr(server, "expert_catalog", None)
    if catalog is not None and catalog.get(template_id) is not None:
        return True
    from octop.infra.market.http import portal_base  # noqa: PLC0415

    if not portal_base():
        logger.warning("skip expert template %s: market catalog is disabled", template_id)
        return False
    paths = getattr(server, "paths", None)
    cache = getattr(paths, "expert_market_dir", None) if paths is not None else None
    if cache is None or catalog is None:
        logger.warning("skip expert template %s: catalog cache is unavailable", template_id)
        return False
    from octop.infra.market import install_portal_expert  # noqa: PLC0415

    try:
        installed = await asyncio.to_thread(install_portal_expert, template_id, cache)
    except Exception as exc:
        logger.warning("expert template %s pull failed: %s", template_id, exc)
        return False
    if installed is None:
        logger.warning("expert template %s is not available from the market", template_id)
        return False
    catalog.refresh()
    if catalog.get(installed.expert_id) is None:
        logger.warning("expert template %s did not load after market install", template_id)
        return False
    return True


async def bootstrap_first_expert(
    server: Any,
    *,
    user_id: int,
    locale: str = "zh",
    agent_id: str | None = None,
    expert_id: str | None = None,
) -> Any | None:
    """Pull *expert_id* from the market when needed, then create the first expert."""
    if server.app_runtime is None:
        logger.warning("skip default agent bootstrap: app_runtime not ready")
        return None
    template_id = (expert_id or "").strip() or DEFAULT_EXPERT_ID
    if not await materialize_market_expert(server, template_id):
        return None
    return await bootstrap_default_agent(
        server.app_runtime.agent_registry,
        server.expert_catalog,
        user_id=user_id,
        locale=locale,
        agent_id=agent_id,
        root_dir=user_policy_workspace_root(server, user_id),
        expert_id=template_id,
    )


async def try_bootstrap_default_agent(
    server: Any,
    *,
    user_id: int,
    locale: str = "zh",
    agent_id: str | None = None,
    expert_id: str | None = None,
) -> None:
    """Best-effort wrapper used by HTTP adapters (setup / invite / new user)."""
    try:
        await bootstrap_first_expert(
            server,
            user_id=user_id,
            locale=locale,
            agent_id=agent_id,
            expert_id=expert_id,
        )
    except Exception as exc:  # pragma: no cover - logged; user creation should still succeed
        logger.warning("could not auto-create default agent for user %s: %s", user_id, exc)
