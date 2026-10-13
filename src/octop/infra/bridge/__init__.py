"""Octop↔Octop instance bridge — remote agents, HTTP tunnel, chat relay."""

from __future__ import annotations

from octop.infra.bridge.ids import (
    BRIDGE_AGENT_PREFIX,
    BridgeAgentRef,
    format_bridge_agent_id,
    parse_bridge_agent_id,
)
from octop.infra.bridge.manager import BridgeManager

__all__ = [
    "BRIDGE_AGENT_PREFIX",
    "BridgeAgentRef",
    "BridgeManager",
    "format_bridge_agent_id",
    "parse_bridge_agent_id",
]
