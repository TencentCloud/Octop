"""Request-scoped MCP catalogs and credential-free execution proxies."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Annotated, Any, NotRequired

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import AgentState, PrivateStateAttr
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool, ToolException
from langgraph.config import get_config
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from octop_harness.mcp import resolve_active_mcp_servers

from octop.i18n.loader import tr
from octop.infra.errors import OctopError
from octop.infra.utils.browser_media import parse_octop_user_id

_SCOPE = "octop_mcp_scope"
_ACTOR: ContextVar[int | None] = ContextVar("octop_mcp_actor", default=None)


@contextmanager
def mcp_actor_scope(user_id: int | None) -> Iterator[None]:
    """Bind the authenticated actor while resuming a checkpointed turn."""
    token = _ACTOR.set(user_id)
    try:
        yield
    finally:
        _ACTOR.reset(token)


class MCPState(AgentState[Any]):
    octop_mcp_scope: NotRequired[Annotated[dict[str, Any], PrivateStateAttr]]


class MCPToolScopeMiddleware(AgentMiddleware[MCPState, Any]):
    """Keep credentials out of the shared graph, including its HITL tool table."""

    state_schema = MCPState

    def __init__(
        self,
        agent: Any,
        validate: Callable[[int, list[str]], list[str]],
        prepare: Callable[[int, list[str]], Awaitable[list[str]]],
    ) -> None:
        self.agent = agent
        self.validate = validate
        self.prepare = prepare
        self.prepared: dict[tuple[int, str], dict[str, BaseTool]] = {}
        self.versions: dict[tuple[int, str], str] = {}
        self.proxies: dict[tuple[str, str], BaseTool] = {}

    def before_agent(self, state: MCPState, runtime: Any) -> dict[str, Any]:
        config = get_config().get("configurable") or {}
        uid = parse_octop_user_id(config.get("user"))
        try:
            servers = resolve_active_mcp_servers(
                mcp_use_default=bool(config.get("mcp_use_default")),
                mcp_servers=config.get("mcp_servers"),
                default_servers=self.agent.config.mcp_default_servers,
            )
        except (TypeError, ValueError):
            servers = None
        # New turns always replace this private field. HITL resumes retain it.
        versions = (
            {name: self.versions.get((uid, name)) for name in servers or []}
            if uid is not None
            else {}
        )
        return {_SCOPE: {"user": uid, "servers": servers or [], "versions": versions}}

    def register(self, uid: int, server: str, tools: list[Any], version: str) -> list[BaseTool]:
        for tool in tools:
            if "octop_mcp_runtime" in tool.args:
                raise ValueError("MCP tool uses the reserved execution-context argument")
            if any(source != server and name == tool.name for source, name in self.proxies):
                raise ValueError("MCP tool name collides with another server")
        self.versions[uid, server] = version
        self.prepared[uid, server] = {tool.name: tool for tool in tools}
        proxies = []
        for tool in tools:
            key = (server, tool.name)
            if key not in self.proxies:
                self.proxies[key] = self._make_proxy(server, tool.name)
            proxies.append(self.proxies[key])
        return proxies

    def _denied(self) -> str:
        return tr("mcp_scope.unauthorized", self.agent.config.language)

    def _make_proxy(self, server: str, name: str) -> BaseTool:
        async def execute(octop_mcp_runtime: ToolRuntime, **arguments: Any) -> Any:
            runtime = octop_mcp_runtime
            tools = await self._selected(runtime.state)
            tool = tools.get(name)
            scope = runtime.state.get(_SCOPE) or {}
            uid = parse_octop_user_id(scope.get("user"))
            # HITL edits happen after wrap_tool_call. Authorize at execution too.
            if (
                uid is None
                or tool is None
                or self.prepared.get((uid, server), {}).get(name) is not tool
            ):
                raise ToolException(self._denied())
            return await tool.ainvoke(arguments, config=runtime.config)

        return StructuredTool.from_function(
            coroutine=execute,
            name=name,
            description=tr("mcp_scope.tool", self.agent.config.language),
            args_schema={"type": "object", "properties": {}, "additionalProperties": True},
            infer_schema=False,
            handle_tool_error=True,
        )

    async def _selected(self, state: Any) -> dict[str, BaseTool]:
        scope = state.get(_SCOPE) or {}
        uid = parse_octop_user_id(scope.get("user"))
        servers = scope.get("servers")
        if uid is None or not isinstance(servers, list) or not servers:
            return {}
        actor = _ACTOR.get()
        if actor is not None and actor != uid:
            return {}
        try:
            approved = self.validate(uid, servers)
        except (OctopError, ValueError, TypeError):
            return {}
        if approved != servers:
            return {}
        if any((uid, server) not in self.prepared for server in servers) and await self.prepare(
            uid, servers
        ):
            return {}
        versions = scope.get("versions")
        if not isinstance(versions, dict) or any(
            not versions.get(server) or versions[server] != self.versions.get((uid, server))
            for server in servers
        ):
            return {}
        selected: dict[str, BaseTool] = {}
        for server in servers:
            tools = self.prepared.get((uid, server))
            if not tools or selected.keys() & tools.keys():
                return {}
            selected.update(tools)
        return selected

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> ModelResponse:
        selected = await self._selected(request.state)
        mcp_names = self.agent._mcp_tool_name_set
        tools = [tool for tool in request.tools or [] if getattr(tool, "name", "") not in mcp_names]
        raw_scope = request.state.get(_SCOPE)
        scope = raw_scope if isinstance(raw_scope, dict) else {}
        uid = parse_octop_user_id(scope.get("user"))
        non_mcp_names = {getattr(tool, "name", "") for tool in tools}
        if uid is None:
            return await handler(request.override(tools=tools))
        for server in scope.get("servers") or []:
            for name, tool in self.prepared.get((uid, server), {}).items():
                if name not in selected or name in non_mcp_names:
                    continue
                proxy = self.proxies[server, name]
                extras = dict(getattr(tool, "extras", None) or {})
                if (
                    self.agent.config.defer_mcp_tools
                    and self.agent.config.tool_search_mode != "eager"
                ):
                    extras["defer_loading"] = True
                tools.append(
                    proxy.model_copy(
                        update={
                            "description": tool.description,
                            "args_schema": tool.args_schema,
                            "extras": extras,
                        }
                    )
                )
        return await handler(request.override(tools=tools))

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        name = str(request.tool_call.get("name") or "")
        if name not in self.agent._mcp_tool_name_set:
            return await handler(request)
        selected = await self._selected(request.state)
        if name not in selected:
            return ToolMessage(
                content=self._denied(),
                tool_call_id=str(request.tool_call.get("id") or ""),
                status="error",
            )
        # Use a wide execution schema; each user's real schema validates after authorization.
        return await handler(request)
