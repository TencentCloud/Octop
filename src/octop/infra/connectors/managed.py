"""Registered handlers for catalog-declared host-managed MCP connectors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from octop.infra.connectors.catalog import ConnectorCatalogEntry
from octop.infra.connectors.open_design import (
    OpenDesignRuntime,
    connection_spec,
    normalize_credentials,
)


class ManagedRuntime(Protocol):
    async def start(self) -> None: ...
    async def shutdown(self) -> None: ...
    def replace_persistence(self, service: Any, repos: Any) -> None: ...
    async def close(self, *, user_id: int | None = None, agent_id: str | None = None) -> None: ...
    async def build_tools(self, *, user_id: int, instance: Any, agent_id: str) -> list[Any]: ...


@dataclass(frozen=True)
class ManagedHandler:
    connection_spec: Callable[[dict[str, Any]], dict[str, Any]]
    normalize_credentials: Callable[[dict[str, Any]], dict[str, Any]]
    create_runtime: Callable[[Any, Any], ManagedRuntime]


# Product registration belongs here, never in AgentManager or the dispatcher.
_HANDLERS = {
    "open-design": ManagedHandler(connection_spec, normalize_credentials, OpenDesignRuntime),
}


def managed_handler(entry: ConnectorCatalogEntry) -> ManagedHandler:
    if entry.mcp_mode != "managed" or entry.runtime_handler not in _HANDLERS:
        raise ValueError(f"unregistered managed MCP handler: {entry.runtime_handler}")
    return _HANDLERS[entry.runtime_handler]
