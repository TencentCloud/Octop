"""Keep a team host on dispatch tools.

The harness prompt still tells every agent to use filesystem tools and
``write_todos``. Those tools are removed from a host, and the model then
prints a raw tool call and stops. This middleware repeats the boundary
after that prompt and drops anything outside the host allowlist.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from octop.i18n import tr
from octop.infra.agents.teams.service import HOST_TOOLS_ALLOWED

_REJECT = "this host only dispatches; ask a member to do that, then send_file_to_user"


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        fn = tool.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            return str(fn["name"])
        return str(tool.get("name") or "")
    return str(getattr(tool, "name", "") or "")


class HostDispatchGuardMiddleware(AgentMiddleware[Any, Any]):
    """Hide non-dispatch tools and say so after the filesystem prompt."""

    def __init__(self, *, locale: str) -> None:
        super().__init__()
        self._note = tr("teams.host_tool_boundary", locale).strip()

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(self._apply(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(self._apply(request))

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        if _tool_name(request.tool_call) in HOST_TOOLS_ALLOWED:
            return handler(request)
        return _reject(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        if _tool_name(request.tool_call) in HOST_TOOLS_ALLOWED:
            return await handler(request)
        return _reject(request)

    def _apply(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        tools = [
            tool for tool in list(request.tools or []) if _tool_name(tool) in HOST_TOOLS_ALLOWED
        ]
        blocks: list[Any] = (
            list(request.system_message.content_blocks) if request.system_message else []
        )
        already = any(
            isinstance(block, dict) and self._note in str(block.get("text") or "")
            for block in blocks
        )
        if not already:
            text = f"\n\n{self._note}" if blocks else self._note
            blocks.append({"type": "text", "text": text})
        return request.override(tools=tools, system_message=SystemMessage(content_blocks=blocks))


def _reject(request: ToolCallRequest) -> ToolMessage:
    raw = request.tool_call.get("id") or request.tool_call.get("tool_call_id") or ""
    return ToolMessage(
        content=f"Error: {_REJECT}",
        name=_tool_name(request.tool_call) or "tool",
        tool_call_id=str(raw),
        status="error",
    )


__all__ = ["HostDispatchGuardMiddleware"]
