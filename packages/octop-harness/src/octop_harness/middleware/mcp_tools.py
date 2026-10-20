"""``MCPToolMiddleware`` — per-request MCP server tool filtering."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.tools.base import BaseTool

from octop_harness.mcp import (
    filter_tools_for_mcp_servers,
    prioritize_active_mcp_tools,
    resolve_active_mcp_servers,
)
from octop_harness.middleware.runtime import runtime_config

logger = logging.getLogger(__name__)


class MCPToolMiddleware(AgentMiddleware[Any, Any]):
    """Expose MCP tools only when the caller opts in on a per-request basis.

    By default (no ``mcp_servers`` / ``mcp_use_default`` on :class:`~octop_harness.request.ChatRequest`)
    all MCP tools are stripped from the model's tool list. Callers must set
    ``mcp_servers=[...]`` or ``mcp_use_default=True`` to enable them.
    """

    def __init__(
        self,
        *,
        server_names: frozenset[str],
        mcp_tool_names: frozenset[str],
        default_servers: list[str] | None,
    ) -> None:
        super().__init__()
        self._server_names = server_names
        self._mcp_tool_names = mcp_tool_names
        self._default_servers = list(default_servers) if default_servers else None

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._apply_filter(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._apply_filter(request))

    def _apply_filter(self, request: ModelRequest) -> ModelRequest:
        configurable = runtime_config(request).get("configurable") or {}
        try:
            active = resolve_active_mcp_servers(
                mcp_use_default=bool(configurable.get("mcp_use_default")),
                mcp_servers=configurable.get("mcp_servers"),
                default_servers=self._default_servers,
            )
        except ValueError:
            logger.warning("Invalid MCP server selection; hiding all MCP tools", exc_info=True)
            active = None

        if active is not None:
            unknown = sorted(set(active) - self._server_names)
            if unknown:
                logger.warning(
                    "ChatRequest references unknown MCP server(s) %s; configured: %s",
                    unknown,
                    sorted(self._server_names),
                )
                active = [s for s in active if s in self._server_names]

        tools_in: list[BaseTool | dict[str, Any]] = list(request.tools or [])
        filtered = filter_tools_for_mcp_servers(
            tools_in,
            mcp_tool_names=self._mcp_tool_names,
            server_names=self._server_names,
            active_servers=active,
        )
        if active:
            filtered = prioritize_active_mcp_tools(
                filtered,
                mcp_tool_names=self._mcp_tool_names,
                active_servers=active,
            )
        mcp_in = sum(1 for t in tools_in if getattr(t, "name", "") in self._mcp_tool_names)
        mcp_out = sum(1 for t in filtered if getattr(t, "name", "") in self._mcp_tool_names)
        ima_out = [getattr(t, "name", "") for t in filtered if "ima" in getattr(t, "name", "")]
        logger.info(
            "MCPToolMiddleware filter: mcp_servers=%s active=%s tools=%d->%d mcp=%d->%d ima=%s",
            configurable.get("mcp_servers"),
            active,
            len(tools_in),
            len(filtered),
            mcp_in,
            mcp_out,
            ima_out[:4],
        )
        return request.override(tools=filtered)


__all__ = ["MCPToolMiddleware"]
