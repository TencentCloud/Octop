"""Hide the harness builtin ``web_fetch`` while DeepSeek's fetch tool is mounted.

DeepSeek's fetch tool intentionally keeps the product-level ``web_fetch`` name.
The harness always mounts its generic HTTP+markdownify ``web_fetch`` builtin, and
exposing two tools with the same name breaks strict tool-calling APIs. When the
DeepSeek-backed replacement is mounted (``HarnessAgentConfig.tools``), this
middleware strips the builtin from the model-visible tool list.

``tools_disabled`` still wins: listing ``web_fetch`` there hides the DeepSeek
tool too, which is the expected "turn web fetching off" behavior.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.tools.base import BaseTool


def _builtin_web_fetch() -> BaseTool:
    # Imported lazily: the harness package pulls in several optional tool
    # dependencies at module import time.
    from octop_harness.builtin.tools import web_fetch as builtin_web_fetch

    return builtin_web_fetch


def _is_builtin_web_fetch(tool: BaseTool | dict[str, Any]) -> bool:
    builtin = _builtin_web_fetch()
    if tool is builtin:
        return True
    return getattr(tool, "func", None) is getattr(builtin, "func", None) and (
        getattr(builtin, "func", None) is not None
    )


class WebFetchOverrideMiddleware(AgentMiddleware[Any, Any]):
    """Remove the harness builtin ``web_fetch`` from the model-visible tools."""

    def _apply(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        tools = list(request.tools or [])
        filtered = [tool for tool in tools if not _is_builtin_web_fetch(tool)]
        if len(filtered) == len(tools):
            return request
        return request.override(tools=filtered)

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


__all__ = ["WebFetchOverrideMiddleware"]
