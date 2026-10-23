"""Soften MCP output-schema validation failures into recoverable tool errors.

When an MCP tool declares an ``outputSchema`` but the server returns structured
content that does not match it (for example ``total`` as the string ``"1"``
against ``{"type": "integer"}``), ``mcp.client.session.ClientSession`` raises a
plain ``RuntimeError`` from ``_validate_tool_result``. Like the ``McpError``
path, that exception is not a ``ToolException``, so it escapes ``ToolNode``
and aborts the whole agent turn before the model receives any tool result
(#2344). ``McpToolErrorMiddleware`` (#2287) deliberately preserves unrelated
``RuntimeError``s; this middleware covers exactly the SDK output-validation
messages, which are distinguishable only by their text.

Unlike an input rejection, the server already accepted the arguments, so the
model is explicitly told that retrying with modified arguments will not help.
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

logger = logging.getLogger(__name__)

_MAX_DETAIL_CHARS = 2000

# Message prefixes/suffix raised by ClientSession._validate_tool_result.
_INVALID_STRUCTURED_CONTENT_PREFIX = "Invalid structured content returned by tool "
_INVALID_SCHEMA_PREFIX = "Invalid schema for tool "
_MISSING_STRUCTURED_CONTENT_SUFFIX = " has an output schema but did not return structured content"

_EXPLANATION = (
    "The MCP server accepted the tool arguments but the returned result failed "
    "the tool's declared output schema. Repeating the call or changing the "
    "arguments is unlikely to fix it. Try a different tool or report the "
    "failure instead of calling this tool again."
)


def _matches_output_validation(message: str) -> bool:
    if message.startswith((_INVALID_STRUCTURED_CONTENT_PREFIX, _INVALID_SCHEMA_PREFIX)):
        return True
    return message.startswith("Tool ") and message.endswith(_MISSING_STRUCTURED_CONTENT_SUFFIX)


def _find_output_validation_error(exc: BaseException) -> RuntimeError | None:
    """Return the first SDK output-validation ``RuntimeError`` inside *exc*.

    The MCP SSE / streamable-HTTP transports run inside anyio task groups, so
    the failure can arrive wrapped in a ``BaseExceptionGroup``. Only the exact
    SDK validation messages are softened; every other ``RuntimeError`` keeps
    propagating (#2287 intentionally leaves those alone).
    """
    if isinstance(exc, RuntimeError) and _matches_output_validation(str(exc)):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            found = _find_output_validation_error(sub)
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


def _error_text(tool_name: str, error: RuntimeError) -> str:
    detail = str(error).strip() or "unknown MCP output validation error"
    if len(detail) > _MAX_DETAIL_CHARS:
        detail = detail[:_MAX_DETAIL_CHARS] + "..."
    return f"MCP tool `{tool_name}` failed output validation: {detail}\n\n{_EXPLANATION}"


def _soften(request: ToolCallRequest, error: RuntimeError) -> ToolMessage:
    tool_call = request.tool_call
    tool_name = str(tool_call.get("name") or "")
    logger.warning("MCP tool %s failed output validation: %s", tool_name, error)
    return ToolMessage(
        content=_error_text(tool_name, error),
        name=tool_name,
        tool_call_id=str(tool_call.get("id") or ""),
        status="error",
    )


class McpToolOutputErrorMiddleware(AgentMiddleware[Any, Any]):
    """Turn MCP output-schema validation failures into failed tool results."""

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        try:
            return handler(request)
        except BaseException as exc:  # noqa: BLE001 - re-raised unless output validation
            if _has_control_flow(exc):
                raise
            error = _find_output_validation_error(exc)
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
        except BaseException as exc:  # noqa: BLE001 - re-raised unless output validation
            if _has_control_flow(exc):
                raise
            error = _find_output_validation_error(exc)
            if error is None:
                raise
            return _soften(request, error)


__all__ = ["McpToolOutputErrorMiddleware"]
