"""Host lifecycle and tool assembly for catalog-declared managed connectors."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from octop.infra.connectors.catalog import get_catalog_entry, list_catalog
from octop.infra.connectors.managed import ManagedRuntime, managed_handler

logger = logging.getLogger(__name__)


class ConnectorRuntime:
    """Dispatch lifecycle and tool assembly through registered catalog capabilities."""

    def __init__(self, service: Any, repos: Any) -> None:
        self._service = service
        self._runtimes: dict[str, ManagedRuntime] = {}
        for entry in list_catalog():
            if entry.mcp_mode == "managed" and entry.runtime_handler not in self._runtimes:
                handler = managed_handler(entry)
                assert entry.runtime_handler is not None
                self._runtimes[entry.runtime_handler] = handler.create_runtime(service, repos)

    def get(self, handler_id: str) -> ManagedRuntime:
        """Resolve a registered runtime for its connector-specific API adapter."""
        return self._runtimes[handler_id]

    async def start(self) -> None:
        for runtime in self._runtimes.values():
            await runtime.start()

    async def shutdown(self) -> None:
        for runtime in self._runtimes.values():
            await runtime.shutdown()

    def replace_persistence(self, service: Any, repos: Any) -> None:
        self._service = service
        for runtime in self._runtimes.values():
            runtime.replace_persistence(service, repos)

    async def close(self, *, user_id: int | None = None, agent_id: str | None = None) -> None:
        for runtime in self._runtimes.values():
            await runtime.close(user_id=user_id, agent_id=agent_id)

    async def prepare_tools(
        self, agent: Any, *, agent_id: str, user_id: int | None, names: list[str]
    ) -> None:
        """Attach selected managed connector tools once per agent runtime."""
        if user_id is None:
            return
        instances = await asyncio.to_thread(
            self._service.list_user_instances,
            user_id,
            active_only=True,
            with_credentials=True,
            include_shared=True,
        )
        for instance in instances:
            entry = get_catalog_entry(instance.kind)
            if (
                instance.mcp_server_name not in names
                or entry is None
                or entry.mcp_mode != "managed"
            ):
                continue
            prefix = f"{instance.mcp_server_name}_"
            if any(t.startswith(prefix) for t in getattr(agent, "_mcp_tool_name_set", frozenset())):
                continue
            try:
                assert entry.runtime_handler is not None
                tools = await self.get(entry.runtime_handler).build_tools(
                    user_id=user_id, instance=instance, agent_id=agent_id
                )
                agent.append_mcp_tools(tools)
            except (Exception, BaseExceptionGroup):
                logger.warning(
                    "Managed tool discovery failed for instance %s", instance.instance_id
                )
