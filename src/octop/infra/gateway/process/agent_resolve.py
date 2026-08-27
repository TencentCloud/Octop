"""Resolve per-agent harness workspace handles for gateway I/O."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.gateway.media.ingress import AgentBackedMediaBackend

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager

logger = logging.getLogger(__name__)


def harness_workspace_for_agent(
    agent_manager: AgentManager,
    agent_id: str,
) -> BackendWorkspace | None:
    """``agent.workspace`` for Dashboard tool media and IM stream projection."""
    try:
        return agent_manager.get_agent(agent_id).workspace
    except Exception:
        logger.debug("harness workspace unavailable for agent %s", agent_id, exc_info=True)
        return None


def media_backend_for_agent(
    agent_manager: AgentManager,
    agent_id: str,
) -> AgentBackedMediaBackend | None:
    """harness-gateway ``MediaBackend`` adapter for IM channel ingress."""
    workspace = harness_workspace_for_agent(agent_manager, agent_id)
    if workspace is None:
        return None
    config = agent_manager.octop_config
    max_bytes = int(config.max_upload_bytes)
    return AgentBackedMediaBackend(workspace, max_bytes=max_bytes)
