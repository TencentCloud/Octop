"""Turn MCP ``McpError`` and output-schema ``RuntimeError`` into failed tool results.

``McpError`` tells the model to fix its arguments. An output-schema failure means
the arguments were already accepted, so the result says not to retry by editing them.
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

_ARGUMENT_HINT = (
    "The MCP server rejected this call. Fix the tool arguments (check types, "
    "required fields and object nesting) and call the tool again."
)
_OUTPUT_NOTE = (
    "The tool accepted the arguments and then failed its own output schema. "
    "Do not retry this call by changing the arguments."
)


def _is_output_schema_message(message: str) -> bool:
    text = message.lstrip()
    return (
        text.startswith("Invalid structured content returned by tool ")
        or text.startswith("Invalid schema for tool ")
        or "has an output schema but did not return structured content" in text
    )


def _find_mcp_error(exc: BaseException) -> McpError | None:
    if isinstance(exc, McpError):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            found = _find_mcp_error(sub)
            if found is not None:
                return found
    return None


def _find_output_schema_error(exc: BaseException) -> RuntimeError | None:
    if isinstance(exc, RuntimeError) and _is_output_schema_message(str(exc)):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            found = _find_output_schema_error(sub)
            if found is not None:
                return found
    return None


def _has_control_flow(exc: BaseException) -> bool:
    if isinstance(exc, (GraphBubbleUp, KeyboardInterrupt, SystemExit)):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_has_control_flow(sub) for sub in exc.exceptions)
    return False


def _clip(detail: str) -> str:
    text = detail.strip() or "unknown MCP error"
    if len(text) > _MAX_DETAIL_CHARS:
        return text[:_MAX_DETAIL_CHARS] + "..."
    return text


def _mcp_error_text(tool_name: str, error: McpError) -> str:
    detail = str(error.error.message or "").strip() or str(error).strip()
    return f"MCP tool `{tool_name}` failed: {_clip(detail)}\n\n{_ARGUMENT_HINT}"


def _output_schema_text(tool_name: str, error: RuntimeError) -> str:
    return f"MCP tool `{tool_name}` failed output-schema validation: {_clip(str(error))}\n\n{_OUTPUT_NOTE}"


def _tool_message(request: ToolCallRequest, content: str) -> ToolMessage:
    tool_call = request.tool_call
    tool_name = str(tool_call.get("name") or "")
    return ToolMessage(
        content=content,
        name=tool_name,
        tool_call_id=str(tool_call.get("id") or ""),
        status="error",
    )


def _soften(request: ToolCallRequest, exc: BaseException) -> ToolMessage | None:
    if _has_control_flow(exc):
        return None
    tool_name = str(request.tool_call.get("name") or "")
    mcp_error = _find_mcp_error(exc)
    if mcp_error is not None:
        logger.warning("MCP tool %s failed: %s", tool_name, mcp_error.error.message)
        return _tool_message(request, _mcp_error_text(tool_name, mcp_error))
    schema_error = _find_output_schema_error(exc)
    if schema_error is not None:
        logger.warning(
            "MCP tool %s failed output-schema validation: %s",
            tool_name,
            str(schema_error)[:500],
        )
        return _tool_message(request, _output_schema_text(tool_name, schema_error))
    return None


class McpToolErrorMiddleware(AgentMiddleware[Any, Any]):
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        try:
            return handler(request)
        except Exception as exc:
            softened = _soften(request, exc)
            if softened is None:
                raise
            return softened

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        try:
            return await handler(request)
        except Exception as exc:
            softened = _soften(request, exc)
            if softened is None:
                raise
            return softened


__all__ = ["McpToolErrorMiddleware"]
