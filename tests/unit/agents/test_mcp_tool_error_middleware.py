"""Tests for McpToolErrorMiddleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.errors import GraphInterrupt
from langgraph.prebuilt.tool_node import ToolCallRequest, ToolNode
from langgraph.runtime import Runtime
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from octop.infra.agents.middleware import mcp_tool_error


def _request(
    name: str = "cls_query_logs", args: dict[str, object] | None = None
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args or {}, "id": "call-1"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


def _mcp_error(message: str) -> McpError:
    return McpError(ErrorData(code=-32602, message=message))


async def test_mcp_error_is_softened_into_error_tool_result() -> None:
    handler = AsyncMock(side_effect=_mcp_error("Validation failed - parameter 'request_body'"))
    request = _request(args={"request_body": "{}"})

    result = await mcp_tool_error.McpToolErrorMiddleware().awrap_tool_call(request, handler)

    assert getattr(result, "status", None) == "error"
    assert getattr(result, "tool_call_id", None) == "call-1"
    content = str(result.content)
    assert "cls_query_logs" in content
    assert "request_body" in content
    assert "call the tool again" in content


async def test_mcp_error_inside_exception_group_is_softened() -> None:
    handler = AsyncMock(side_effect=ExceptionGroup("mcp", [_mcp_error("Tool execution failed")]))
    request = _request()

    result = await mcp_tool_error.McpToolErrorMiddleware().awrap_tool_call(request, handler)

    assert getattr(result, "status", None) == "error"
    assert "Tool execution failed" in str(result.content)


async def test_non_mcp_error_still_propagates() -> None:
    handler = AsyncMock(side_effect=RuntimeError("boom"))
    request = _request()

    with pytest.raises(RuntimeError, match="boom"):
        await mcp_tool_error.McpToolErrorMiddleware().awrap_tool_call(request, handler)


async def test_graph_interrupt_is_not_swallowed() -> None:
    handler = AsyncMock(side_effect=GraphInterrupt())
    request = _request()

    with pytest.raises(GraphInterrupt):
        await mcp_tool_error.McpToolErrorMiddleware().awrap_tool_call(request, handler)


async def test_graph_interrupt_grouped_with_mcp_error_is_not_swallowed() -> None:
    """A group carrying both must not be softened: the interrupt must surface."""
    group = ExceptionGroup("mixed", [GraphInterrupt(), _mcp_error("Tool execution failed")])
    handler = AsyncMock(side_effect=group)
    request = _request()

    with pytest.raises(BaseExceptionGroup):
        await mcp_tool_error.McpToolErrorMiddleware().awrap_tool_call(request, handler)


async def test_successful_call_is_untouched() -> None:
    sentinel = object()
    handler = AsyncMock(return_value=sentinel)
    request = _request()

    result = await mcp_tool_error.McpToolErrorMiddleware().awrap_tool_call(request, handler)

    assert result is sentinel


def test_sync_path_softens_mcp_error() -> None:
    def handler(_request: ToolCallRequest) -> Any:
        raise _mcp_error("Tool execution failed")

    result = mcp_tool_error.McpToolErrorMiddleware().wrap_tool_call(_request(), handler)

    assert getattr(result, "status", None) == "error"
    assert "Tool execution failed" in str(result.content)


def _failing_mcp_tool() -> StructuredTool:
    """A tool shaped like ``langchain_mcp_adapters`` output that raises ``McpError``."""

    async def _call(**_kwargs: Any) -> str:
        raise _mcp_error(
            "Tool execution failed: Validation failed - parameter 'request_body' "
            'is not of type "object"'
        )

    return StructuredTool(
        name="cls_query_logs",
        description="query logs",
        args_schema={"type": "object", "properties": {}},
        coroutine=_call,
    )


def _runtime_config() -> dict[str, Any]:
    """Minimal runnable config carrying the ``Runtime`` ToolNode expects."""
    from langgraph._internal._constants import CONF, CONFIG_KEY_RUNTIME

    return {CONF: {CONFIG_KEY_RUNTIME: Runtime(context=None)}}


def _tool_call_message() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "cls_query_logs",
                "args": {"request_body": "{}"},
                "id": "call-1",
            }
        ],
    )


async def test_tool_node_returns_error_result_instead_of_aborting() -> None:
    """The reported symptom: an MCP validation error must not kill the task."""
    middleware = mcp_tool_error.McpToolErrorMiddleware()

    async def awrap(
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Any]],
    ) -> ToolMessage | Any:
        return await middleware.awrap_tool_call(request, handler)

    node = ToolNode(tools=[_failing_mcp_tool()], awrap_tool_call=awrap)

    result = await node.ainvoke({"messages": [_tool_call_message()]}, _runtime_config())

    outputs = result["messages"]
    assert len(outputs) == 1
    tool_message = outputs[0]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.status == "error"
    assert tool_message.tool_call_id == "call-1"
    assert "request_body" in str(tool_message.content)


async def test_tool_node_still_raises_without_the_middleware() -> None:
    """Guards the regression: without the fix the same call aborts the task."""
    node = ToolNode(tools=[_failing_mcp_tool()])

    with pytest.raises(McpError):
        await node.ainvoke({"messages": [_tool_call_message()]}, _runtime_config())
