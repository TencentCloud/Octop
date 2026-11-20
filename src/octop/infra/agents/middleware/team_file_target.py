"""Give a team member the target workspace's file tools for one turn.

The target travels in ``configurable``: the host workspace, or a directory on
the chat initiator. File tools keep their names. Execution goes through
``BackendWorkspace`` (the same path the managed MCP server uses), and
``send_file_to_user`` reads that workspace. This middleware does not change
one-to-one chats, and it does not touch skills or memory reads.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import ToolCall, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.config import get_config
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from pydantic import ConfigDict

from octop.infra.agents.acp.team_workspace_mcp import TeamWorkspaceScope, run_workspace_tool
from octop.infra.agents.teams.file_target import (
    BRIDGE_TARGET_KEY,
    DIR_KEY,
    HOST_KEY,
    capability_enabled,
    workspace_file_args,
)
from octop.infra.agents.teams.file_target_guard import install_file_target_guards
from octop.infra.bridge.local_workspace import lookup_peer_target

logger = logging.getLogger(__name__)

_FILE_TOOLS = frozenset({"ls", "read_file", "write_file", "edit_file", "glob", "grep", "delete"})
_SEND_TOOLS = frozenset({"send_file", "send_file_to_user"})
_EXECUTE = "execute"
_WORKSPACE_TOOLS = _FILE_TOOLS | _SEND_TOOLS
_ANNOTATED = _WORKSPACE_TOOLS | {_EXECUTE}

install_file_target_guards()


def _tool_name(tool: BaseTool | dict[str, Any]) -> str:
    if isinstance(tool, dict):
        fn = tool.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            return str(fn["name"])
        if tool.get("name"):
            return str(tool["name"])
        return ""
    return str(getattr(tool, "name", "") or "")


def _base(name: str) -> str:
    return name.rsplit("/", 1)[-1]


class TeamFileTargetMiddleware(AgentMiddleware[Any, Any]):
    """Bind file tools to the host workspace stamped on this turn."""

    def __init__(self, *, agent_id: str, lookup: Callable[[str], Any]) -> None:
        super().__init__()
        self._agent_id = agent_id
        self._lookup = lookup

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(self._prepare_tools(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(self._prepare_tools(request))

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        routed = self._route(request)
        if routed is None:
            return handler(request)
        name, host = routed
        if isinstance(host, ToolMessage):
            return host
        request = self._interpret_request(request)
        bound = self._bind_workspace_tool(request, name, host)
        if isinstance(bound, ToolMessage):
            return bound
        return handler(bound)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        routed = self._route(request)
        if routed is None:
            return await handler(request)
        name, host = routed
        if isinstance(host, ToolMessage):
            return host
        request = self._interpret_request(request)
        bound = self._bind_workspace_tool(request, name, host)
        if isinstance(bound, ToolMessage):
            return bound
        return await handler(bound)

    def _prepare_tools(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        configurable = _configurable()
        tools = list(request.tools or [])
        if not capability_enabled(configurable, "execute"):
            tools = [tool for tool in tools if _base(_tool_name(tool)) != _EXECUTE]
        directory = configurable.get(DIR_KEY)
        if isinstance(directory, str) and directory.strip():
            suffix = (
                f" This turn's default workspace is {directory.strip()}. "
                "Relative paths resolve from there, not from your private workspace."
            )
            tools = [_annotate_tool(tool, suffix) for tool in tools]
        if tools == list(request.tools or []):
            return request
        return request.override(tools=tools)

    def _route(self, request: ToolCallRequest) -> tuple[str, Any] | None:
        name = _base(str(request.tool_call.get("name") or ""))
        if name not in _FILE_TOOLS and name not in _SEND_TOOLS and name != _EXECUTE:
            return None
        configurable = _configurable()
        bridge_id = configurable.get(BRIDGE_TARGET_KEY)
        if isinstance(bridge_id, str) and bridge_id.strip():
            target = lookup_peer_target(bridge_id.strip())
            if target is None:
                return name, _error(request, "the local workspace is not available")
            return name, target
        if not configurable.get(HOST_KEY):
            return None
        host = self._host_agent()
        if host is None:
            return name, _error(request, "the team host workspace is not available")
        return name, host

    def _bind_workspace_tool(
        self, request: ToolCallRequest, name: str, host: Any
    ) -> ToolCallRequest | ToolMessage:
        """Run this call through the target ``BackendWorkspace``."""
        if getattr(host, "bridge_file_target", False):
            workspace: Any = host
            backend: Any = host
        else:
            workspace = getattr(host, "workspace", None)
            backend = getattr(host, "backend", None)
        if workspace is None or backend is None:
            return _error(request, "the team host workspace is not available")
        tool = _WorkspaceTool(
            name=name,
            op=name,
            workspace=workspace,
            backend=backend,
            scope=self._scope(),
        )
        call: ToolCall = {
            "name": str(request.tool_call.get("name") or name),
            "args": _args(request),
            "id": request.tool_call.get("id"),
        }
        return request.override(tool=tool, tool_call=call)

    def _interpret_request(self, request: ToolCallRequest) -> ToolCallRequest:
        """Resolve file paths against the target directory before the tool runs."""
        target = str(_configurable().get(DIR_KEY) or "")
        updated = workspace_file_args(_args(request), target_dir=target)
        call: ToolCall = {
            "name": str(request.tool_call.get("name") or ""),
            "args": updated,
            "id": request.tool_call.get("id"),
        }
        request.tool_call = call
        return request

    def _scope(self) -> TeamWorkspaceScope:
        cfg = _configurable()
        return TeamWorkspaceScope(
            host_agent_id=str(cfg.get(HOST_KEY) or ""),
            directory=str(cfg.get(DIR_KEY) or ""),
            execute=capability_enabled(cfg, "execute"),
            bridge_target_id=str(cfg.get(BRIDGE_TARGET_KEY) or ""),
            deliver=True,
        )

    def _host_agent(self) -> Any | None:
        host_id = _configurable().get(HOST_KEY)
        if not isinstance(host_id, str) or not host_id.strip():
            return None
        try:
            return self._lookup(host_id.strip())
        except Exception:
            logger.debug("team file target host %s is not running", host_id, exc_info=True)
            return None


class _WorkspaceTool(BaseTool):
    """One file or send call against the turn's ``BackendWorkspace``."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str = "Read and write the selected workspace."
    op: str = ""
    workspace: Any = None
    backend: Any = None
    scope: TeamWorkspaceScope | None = None

    def _run(self, *args: Any, **kwargs: Any) -> str:
        return asyncio.run(self._go(_call_payload(args, kwargs)))

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return await self._go(_call_payload(args, kwargs))

    async def _go(self, payload: dict[str, Any]) -> str:
        return await run_workspace_tool(
            self.op or self.name,
            payload,
            scope=self.scope or TeamWorkspaceScope(host_agent_id="", directory="", execute=False),
            workspace=self.workspace,
            backend=self.backend,
        )

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> str:
        del config, kwargs
        return asyncio.run(self._go(_call_payload(input)))

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> str:
        del config, kwargs
        return await self._go(_call_payload(input))


def _call_payload(raw: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(raw, tuple) and raw:
        raw = raw[0]
    if isinstance(raw, dict):
        nested = raw.get("args")
        if isinstance(nested, dict):
            return dict(nested)
        if "name" in raw or "id" in raw or "type" in raw:
            return {}
        return dict(raw)
    if extra:
        return dict(extra)
    return {}


def _annotate_tool(tool: BaseTool | dict[str, Any], suffix: str) -> BaseTool | dict[str, Any]:
    if _base(_tool_name(tool)) not in _ANNOTATED:
        return tool
    if isinstance(tool, dict):
        copied = dict(tool)
        function = copied.get("function")
        if isinstance(function, dict):
            function = dict(function)
            function["description"] = str(function.get("description") or "") + suffix
            copied["function"] = function
            return copied
        copied["description"] = str(copied.get("description") or "") + suffix
        return copied
    description = str(getattr(tool, "description", "") or "")
    clone = getattr(tool, "model_copy", None)
    if not callable(clone):
        return tool
    try:
        return cast(
            "BaseTool | dict[str, Any]",
            clone(update={"description": description + suffix}),
        )
    except Exception:
        logger.debug("team file target could not annotate %s", _tool_name(tool), exc_info=True)
        return tool


def _configurable() -> dict[str, Any]:
    try:
        raw = get_config().get("configurable") or {}
    except RuntimeError:
        return {}
    return dict(raw) if isinstance(raw, dict) else {}


def _args(request: ToolCallRequest) -> dict[str, Any]:
    raw = request.tool_call.get("args")
    return dict(raw) if isinstance(raw, dict) else {}


def _call_id(request: ToolCallRequest) -> str:
    raw = request.tool_call.get("id") or request.tool_call.get("tool_call_id") or ""
    return str(raw)


def _error(request: ToolCallRequest, text: str) -> ToolMessage:
    return ToolMessage(
        content=f"Error: {text}",
        name=_base(str(request.tool_call.get("name") or "execute")),
        tool_call_id=_call_id(request),
        status="error",
    )


__all__ = ["TeamFileTargetMiddleware"]
