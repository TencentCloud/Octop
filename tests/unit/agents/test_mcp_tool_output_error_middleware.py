"""Tests for McpToolOutputErrorMiddleware."""

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

from octop.infra.agents.middleware import mcp_tool_output_error

# Exact message shape raised by mcp.client.session.ClientSession._validate_tool_result
# on the reported Tencent Docs failure (#2344).
_REPORTED_MESSAGE = (
    "Invalid structured content returned by tool manage.search_file: '1' is not of type 'integer'"
)


def _request(
    name: str = "manage.search_file", args: dict[str, object] | None = None
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args or {}, "id": "call-1"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


async def test_reported_failure_is_softened_into_error_tool_result() -> None:
    handler = AsyncMock(side_effect=RuntimeError(_REPORTED_MESSAGE))
    request = _request(args={"search_key": "example document"})

    result = await mcp_tool_output_error.McpToolOutputErrorMiddleware().awrap_tool_call(
        request, handler
    )

    assert getattr(result, "status", None) == "error"
    assert getattr(result, "tool_call_id", None) == "call-1"
    content = str(result.content)
    assert "manage.search_file" in content
    assert "'1' is not of type 'integer'" in content


async def test_softened_message_does_not_tell_model_to_fix_arguments() -> None:
    """Output failures must not trigger argument-fixing retries (#2344)."""
    handler = AsyncMock(side_effect=RuntimeError(_REPORTED_MESSAGE))
    request = _request()

    result = await mcp_tool_output_error.McpToolOutputErrorMiddleware().awrap_tool_call(
        request, handler
    )

    content = str(result.content).lower()
    assert "accepted the tool arguments" in content
    assert "output schema" in content
    assert "fix the tool arguments" not in content
    assert "call the tool again" not in content


async def test_missing_structured_content_failure_is_softened() -> None:
    handler = AsyncMock(
        side_effect=RuntimeError(
            "Tool manage.search_file has an output schema but did not return structured content"
        )
    )
    request = _request()

    result = await mcp_tool_output_error.McpToolOutputErrorMiddleware().awrap_tool_call(
        request, handler
    )

    assert getattr(result, "status", None) == "error"
    assert "did not return structured content" in str(result.content)


async def test_invalid_schema_failure_is_softened() -> None:
    handler = AsyncMock(
        side_effect=RuntimeError("Invalid schema for tool manage.search_file: bad schema")
    )
    request = _request()

    result = await mcp_tool_output_error.McpToolOutputErrorMiddleware().awrap_tool_call(
        request, handler
    )

    assert getattr(result, "status", None) == "error"
    assert "Invalid schema" in str(result.content)


async def test_output_validation_error_inside_exception_group_is_softened() -> None:
    handler = AsyncMock(side_effect=ExceptionGroup("mcp", [RuntimeError(_REPORTED_MESSAGE)]))
    request = _request()

    result = await mcp_tool_output_error.McpToolOutputErrorMiddleware().awrap_tool_call(
        request, handler
    )

    assert getattr(result, "status", None) == "error"
    assert "'1' is not of type 'integer'" in str(result.content)


async def test_other_runtime_errors_still_propagate() -> None:
    handler = AsyncMock(side_effect=RuntimeError("boom"))
    request = _request()

    with pytest.raises(RuntimeError, match="boom"):
        await mcp_tool_output_error.McpToolOutputErrorMiddleware().awrap_tool_call(request, handler)


async def test_similar_but_unrelated_messages_still_propagate() -> None:
    """Only the exact SDK validation messages are softened, not look-alikes."""
    handler = AsyncMock(
        side_effect=RuntimeError("Invalid structured content returned from upstream cache")
    )
    request = _request()

    with pytest.raises(RuntimeError):
        await mcp_tool_output_error.McpToolOutputErrorMiddleware().awrap_tool_call(request, handler)


async def test_graph_interrupt_is_not_swallowed() -> None:
    handler = AsyncMock(side_effect=GraphInterrupt())
    request = _request()

    with pytest.raises(GraphInterrupt):
        await mcp_tool_output_error.McpToolOutputErrorMiddleware().awrap_tool_call(request, handler)


async def test_graph_interrupt_grouped_with_output_error_is_not_swallowed() -> None:
    """A group carrying both must not be softened: the interrupt must surface."""
    group = ExceptionGroup("mixed", [GraphInterrupt(), RuntimeError(_REPORTED_MESSAGE)])
    handler = AsyncMock(side_effect=group)
    request = _request()

    with pytest.raises(BaseExceptionGroup):
        await mcp_tool_output_error.McpToolOutputErrorMiddleware().awrap_tool_call(request, handler)


async def test_successful_call_is_untouched() -> None:
    sentinel = object()
    handler = AsyncMock(return_value=sentinel)
    request = _request()

    result = await mcp_tool_output_error.McpToolOutputErrorMiddleware().awrap_tool_call(
        request, handler
    )

    assert result is sentinel


def test_sync_path_softens_output_validation_error() -> None:
    def handler(_request: ToolCallRequest) -> Any:
        raise RuntimeError(_REPORTED_MESSAGE)

    result = mcp_tool_output_error.McpToolOutputErrorMiddleware().wrap_tool_call(
        _request(), handler
    )

    assert getattr(result, "status", None) == "error"
    assert "'1' is not of type 'integer'" in str(result.content)


def test_detail_is_truncated() -> None:
    long_detail = "x" * 5000
    text = mcp_tool_output_error._error_text(
        "manage.search_file", RuntimeError(f"{_REPORTED_MESSAGE}{long_detail}")
    )

    assert len(text) < len(_REPORTED_MESSAGE) + 5000
    assert "..." in text


def _failing_mcp_tool() -> StructuredTool:
    """A tool shaped like ``langchain_mcp_adapters`` output that hits SDK validation."""

    async def _call(**_kwargs: Any) -> str:
        raise RuntimeError(_REPORTED_MESSAGE)

    return StructuredTool(
        name="manage.search_file",
        description="search documents",
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
                "name": "manage.search_file",
                "args": {"search_key": "example document"},
                "id": "call-1",
            }
        ],
    )


async def test_tool_node_returns_error_result_instead_of_aborting() -> None:
    """The reported symptom: an output-validation failure must not kill the turn."""
    middleware = mcp_tool_output_error.McpToolOutputErrorMiddleware()

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
    assert "'1' is not of type 'integer'" in str(tool_message.content)


async def test_tool_node_still_raises_without_the_middleware() -> None:
    """Guards the regression: without the fix the same call aborts the turn."""
    node = ToolNode(tools=[_failing_mcp_tool()])

    with pytest.raises(RuntimeError, match="Invalid structured content"):
        await node.ainvoke({"messages": [_tool_call_message()]}, _runtime_config())
