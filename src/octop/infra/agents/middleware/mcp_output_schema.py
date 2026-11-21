"""Output-schema MCP failures for harness builds without ``McpToolErrorMiddleware``."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

logger = logging.getLogger(__name__)

_MAX_DETAIL_CHARS = 2000

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


def _error_text(tool_name: str, error: RuntimeError) -> str:
    detail = str(error).strip() or "invalid structured content"
    if len(detail) > _MAX_DETAIL_CHARS:
        detail = detail[:_MAX_DETAIL_CHARS] + "..."
    return f"MCP tool `{tool_name}` failed output-schema validation: {detail}\n\n{_OUTPUT_NOTE}"


def _soften(request: ToolCallRequest, error: RuntimeError) -> ToolMessage:
    tool_call = request.tool_call
    tool_name = str(tool_call.get("name") or "")
    logger.warning(
        "MCP tool %s failed output-schema validation: %s",
        tool_name,
        str(error)[:500],
    )
    return ToolMessage(
        content=_error_text(tool_name, error),
        name=tool_name,
        tool_call_id=str(tool_call.get("id") or ""),
        status="error",
    )


class McpOutputSchemaMiddleware(AgentMiddleware[Any, Any]):
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        try:
            return handler(request)
        except BaseException as exc:
            if _has_control_flow(exc):
                raise
            error = _find_output_schema_error(exc)
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
        except BaseException as exc:
            if _has_control_flow(exc):
                raise
            error = _find_output_schema_error(exc)
            if error is None:
                raise
            return _soften(request, error)


def harness_handles_mcp_tool_errors() -> bool:
    try:
        from octop_harness.middleware.mcp_tool_error import McpToolErrorMiddleware
    except ImportError:
        return False
    return McpToolErrorMiddleware is not None


__all__ = ["McpOutputSchemaMiddleware", "harness_handles_mcp_tool_errors"]
