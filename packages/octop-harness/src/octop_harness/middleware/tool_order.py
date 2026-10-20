"""Stable model-facing tool ordering for parent/subagent cache reuse."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse


def _tool_name(tool: Any) -> str | None:
    """Return a LangChain/OpenAI tool name without changing the tool object."""
    name = getattr(tool, "name", None)
    if isinstance(name, str):
        return name
    if not isinstance(tool, dict):
        return None
    function = tool.get("function")
    if isinstance(function, dict):
        fname = function.get("name")
        if isinstance(fname, str):
            return fname
    raw_name = tool.get("name")
    return raw_name if isinstance(raw_name, str) else None


def move_tools_to_end(tools: Sequence[Any], names: frozenset[str]) -> list[Any]:
    """Move named tools to the tail while preserving both partitions' order."""
    leading: list[Any] = []
    trailing: list[Any] = []
    for tool in tools:
        (trailing if _tool_name(tool) in names else leading).append(tool)
    return [*leading, *trailing]


class TaskToolLastMiddleware(AgentMiddleware[Any, Any]):
    """Place ``task`` after parent/child shared tools in model requests.

    LangChain assembles middleware-provided tools before regular tools. DeepAgents
    provides ``task`` through middleware, so without this final request-time
    normalization the parent diverges from its child before all regular tools.
    Tool execution is unaffected: only the list bound to the model is reordered.
    """

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._reorder(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._reorder(request))

    @staticmethod
    def _reorder(request: ModelRequest) -> ModelRequest:
        reordered = move_tools_to_end(request.tools, frozenset({"task"}))
        if reordered == list(request.tools):
            return request
        return request.override(tools=reordered)


__all__ = ["TaskToolLastMiddleware", "move_tools_to_end"]
