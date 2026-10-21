"""Reject tool calls for names hidden by the agent tools denylist."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command


class DisabledToolsMiddleware(AgentMiddleware[Any, Any]):
    """Enforce ``tools_disabled`` at dispatch time, not only at model listing.

    Tool visibility is a model-facing hint; a stale or hand-crafted call can
    still name a hidden tool. Returning an error ToolMessage without invoking
    the downstream handler keeps disabled tools side-effect free.
    """

    def __init__(self, disabled: Iterable[str] = ()) -> None:
        super().__init__()
        self._disabled = frozenset(str(name).strip() for name in disabled if str(name).strip())

    def _reject(self, request: ToolCallRequest) -> ToolMessage | None:
        name = str(request.tool_call.get("name") or "").rsplit("/", 1)[-1]
        if name not in self._disabled:
            return None
        return ToolMessage(
            content=f"Tool {name!r} is disabled for this agent",
            tool_call_id=str(request.tool_call.get("id") or ""),
            status="error",
            name=name,
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        rejected = self._reject(request)
        return rejected if rejected is not None else handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        rejected = self._reject(request)
        return rejected if rejected is not None else await handler(request)
