"""Soften MCP protocol errors into recoverable tool errors.

When an MCP server rejects a tool call (for example because the model sent
``request_body`` as a JSON string instead of an object), the MCP client raises
``mcp.shared.exceptions.McpError``. That exception is **not** a
``ToolException``, so LangChain's ``handle_tool_error`` callback never sees
it: it escapes ``ToolNode`` and aborts the whole task.

``langchain_mcp_adapters`` already softens ``CallToolResult(isError=True)``
results the same way — this middleware covers the remaining gap, the
JSON-RPC error path, so the agent gets a failed tool result and can correct
its arguments instead of the task dying.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from mcp.shared.exceptions import McpError

logger = logging.getLogger(__name__)

_MAX_DETAIL_CHARS = 2000

_RETRY_HINT = (
    "The MCP server rejected this call. Fix the tool arguments (check types, "
    "required fields and object nesting) and call the tool again."
)


def _find_mcp_error(exc: BaseException) -> McpError | None:
    """Return the first ``McpError`` inside *exc*, unwrapping exception groups.

    The MCP SSE / streamable-HTTP transports run inside anyio task groups, so
    a transport failure can arrive wrapped in a ``BaseExceptionGroup``. Only
    groups that actually carry an ``McpError`` are softened; everything else
    keeps propagating.
    """
    if isinstance(exc, McpError):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            found = _find_mcp_error(sub)
            if found is not None:
                return found
    return None


def _has_control_flow(exc: BaseException) -> bool:
    """True when *exc* (or a nested member) is a control-flow signal.

    ``GraphInterrupt`` derives from ``BaseException`` (not ``Exception``), so a
    blanket ``except BaseException`` would silently swallow interrupts and
    turn them into tool errors. Keyboard / system exits are treated the same.
    """
    if isinstance(exc, (GraphBubbleUp, KeyboardInterrupt, SystemExit)):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_has_control_flow(sub) for sub in exc.exceptions)
    return False


def _error_text(tool_name: str, error: McpError) -> str:
    detail = str(error.error.message or "").strip()
    if not detail:
        detail = str(error).strip() or "unknown MCP error"
    if len(detail) > _MAX_DETAIL_CHARS:
        detail = detail[:_MAX_DETAIL_CHARS] + "..."
    return f"MCP tool `{tool_name}` failed: {detail}\n\n{_RETRY_HINT}"


def _soften(request: ToolCallRequest, error: McpError) -> ToolMessage:
    tool_call = request.tool_call
    tool_name = str(tool_call.get("name") or "")
    logger.warning("MCP tool %s failed: %s", tool_name, error.error.message)
    return ToolMessage(
        content=_error_text(tool_name, error),
        name=tool_name,
        tool_call_id=str(tool_call.get("id") or ""),
        status="error",
    )


class McpToolErrorMiddleware(AgentMiddleware[Any, Any]):
    """Turn MCP tool failures into failed tool results the agent can retry."""

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        try:
            return handler(request)
        except BaseException as exc:  # noqa: BLE001 - re-raised unless it is an MCP error
            if _has_control_flow(exc):
                raise
            error = _find_mcp_error(exc)
            if error is None:
                raise
            return _soften(request, error)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        try:
            return await handler(request)
        except BaseException as exc:  # noqa: BLE001 - re-raised unless it is an MCP error
            if _has_control_flow(exc):
                raise
            error = _find_mcp_error(exc)
            if error is None:
                raise
            return _soften(request, error)


__all__ = ["McpToolErrorMiddleware"]
