"""MCP output-schema validation failures stay inside the tool result."""

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

from octop.infra.agents.middleware import mcp_output_schema

_SCHEMA_ERROR = RuntimeError(
    "Invalid structured content returned by tool manage.search_file: "
    "'1' is not of type 'integer'\n"
    "Failed validating 'type' in schema['properties']['total']:\n"
    "    {'type': 'integer'}\n"
    "On instance['total']:\n"
    "    '1'"
)


def _request(name: str = "tencent-docs_manage.search_file") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={
            "name": name,
            "args": {"search_key": "example document"},
            "id": "call-1",
        },
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


async def test_output_schema_error_is_a_failed_tool_result() -> None:
    handler = AsyncMock(side_effect=_SCHEMA_ERROR)

    result = await mcp_output_schema.McpOutputSchemaMiddleware().awrap_tool_call(
        _request(), handler
    )

    assert getattr(result, "status", None) == "error"
    assert getattr(result, "tool_call_id", None) == "call-1"
    content = str(result.content)
    assert "tencent-docs_manage.search_file" in content
    assert "'1' is not of type 'integer'" in content
    assert "Do not retry this call by changing the arguments." in content
    assert "call the tool again" not in content.lower()
    assert "fix the tool arguments" not in content.lower()


async def test_missing_structured_content_is_softened() -> None:
    handler = AsyncMock(
        side_effect=RuntimeError(
            "Tool manage.search_file has an output schema but did not return structured content"
        )
    )

    result = await mcp_output_schema.McpOutputSchemaMiddleware().awrap_tool_call(
        _request(), handler
    )

    assert getattr(result, "status", None) == "error"
    assert "did not return structured content" in str(result.content)


async def test_invalid_output_schema_is_softened() -> None:
    handler = AsyncMock(side_effect=RuntimeError("Invalid schema for tool manage.search_file: x"))

    result = await mcp_output_schema.McpOutputSchemaMiddleware().awrap_tool_call(
        _request(), handler
    )

    assert getattr(result, "status", None) == "error"


async def test_output_schema_error_inside_exception_group_is_softened() -> None:
    handler = AsyncMock(side_effect=ExceptionGroup("mcp", [_SCHEMA_ERROR]))

    result = await mcp_output_schema.McpOutputSchemaMiddleware().awrap_tool_call(
        _request(), handler
    )

    assert getattr(result, "status", None) == "error"
    assert "not of type 'integer'" in str(result.content)


async def test_other_runtime_error_still_propagates() -> None:
    handler = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        await mcp_output_schema.McpOutputSchemaMiddleware().awrap_tool_call(_request(), handler)


async def test_graph_interrupt_is_not_swallowed() -> None:
    handler = AsyncMock(side_effect=GraphInterrupt())

    with pytest.raises(GraphInterrupt):
        await mcp_output_schema.McpOutputSchemaMiddleware().awrap_tool_call(_request(), handler)


async def test_graph_interrupt_grouped_with_schema_error_is_not_swallowed() -> None:
    group = ExceptionGroup("mixed", [GraphInterrupt(), _SCHEMA_ERROR])
    handler = AsyncMock(side_effect=group)

    with pytest.raises(BaseExceptionGroup):
        await mcp_output_schema.McpOutputSchemaMiddleware().awrap_tool_call(_request(), handler)


async def test_successful_call_is_untouched() -> None:
    sentinel = object()
    handler = AsyncMock(return_value=sentinel)

    result = await mcp_output_schema.McpOutputSchemaMiddleware().awrap_tool_call(
        _request(), handler
    )

    assert result is sentinel


def test_sync_path_softens_output_schema_error() -> None:
    def handler(_request: ToolCallRequest) -> Any:
        raise _SCHEMA_ERROR

    result = mcp_output_schema.McpOutputSchemaMiddleware().wrap_tool_call(_request(), handler)

    assert getattr(result, "status", None) == "error"
    assert "not of type 'integer'" in str(result.content)


async def test_long_detail_is_truncated() -> None:
    error = RuntimeError("Invalid structured content returned by tool demo: " + ("x" * 3000))
    handler = AsyncMock(side_effect=error)

    result = await mcp_output_schema.McpOutputSchemaMiddleware().awrap_tool_call(
        _request("demo"), handler
    )

    content = str(result.content)
    assert "..." in content
    assert content.endswith("Do not retry this call by changing the arguments.")
    assert "x" * 2500 not in content


def _runtime_config() -> dict[str, Any]:
    from langgraph._internal._constants import CONF, CONFIG_KEY_RUNTIME

    return {CONF: {CONFIG_KEY_RUNTIME: Runtime(context=None)}}


def _tool_call_message() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "tencent-docs_manage.search_file",
                "args": {"search_key": "example document"},
                "id": "call-1",
            }
        ],
    )


def _schema_tool() -> StructuredTool:
    async def _call(**_kwargs: Any) -> str:
        raise _SCHEMA_ERROR

    return StructuredTool(
        name="tencent-docs_manage.search_file",
        description="search documents",
        args_schema={"type": "object", "properties": {"search_key": {"type": "string"}}},
        coroutine=_call,
    )


async def test_tool_node_returns_error_result_instead_of_aborting() -> None:
    middleware = mcp_output_schema.McpOutputSchemaMiddleware()

    async def awrap(
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Any]],
    ) -> ToolMessage | Any:
        return await middleware.awrap_tool_call(request, handler)

    node = ToolNode(tools=[_schema_tool()], awrap_tool_call=awrap)
    result = await node.ainvoke({"messages": [_tool_call_message()]}, _runtime_config())

    outputs = result["messages"]
    assert len(outputs) == 1
    tool_message = outputs[0]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.status == "error"
    assert tool_message.tool_call_id == "call-1"
    assert "not of type 'integer'" in str(tool_message.content)
    assert "changing the arguments" in str(tool_message.content)


async def test_tool_node_still_raises_without_the_middleware() -> None:
    node = ToolNode(tools=[_schema_tool()])

    with pytest.raises(RuntimeError, match="not of type 'integer'"):
        await node.ainvoke({"messages": [_tool_call_message()]}, _runtime_config())


async def test_real_sdk_string_total_is_softened() -> None:
    """The installed MCP client rejects string ``total``; the turn must survive."""
    import anyio
    from mcp import ClientSession, types

    incoming_send, incoming_receive = anyio.create_memory_object_stream(1)
    outgoing_send, outgoing_receive = anyio.create_memory_object_stream(1)
    session = ClientSession(incoming_receive, outgoing_send)
    schema = {"type": "object", "properties": {"total": {"type": "integer"}}}
    session._tool_output_schemas["manage.search_file"] = schema
    session.send_request = AsyncMock(
        return_value=types.CallToolResult(
            content=[types.TextContent(type="text", text='{"total": 1}')],
            structuredContent={"total": "1"},
            isError=False,
        )
    )

    async def _call(**_kwargs: Any) -> str:
        await session.call_tool("manage.search_file", {"search_key": "example document"})
        return "unreachable"

    tool = StructuredTool(
        name="tencent-docs_manage.search_file",
        description="search documents",
        args_schema={"type": "object", "properties": {"search_key": {"type": "string"}}},
        coroutine=_call,
    )
    middleware = mcp_output_schema.McpOutputSchemaMiddleware()

    async def awrap(
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Any]],
    ) -> ToolMessage | Any:
        return await middleware.awrap_tool_call(request, handler)

    try:
        node = ToolNode(tools=[tool], awrap_tool_call=awrap)
        result = await node.ainvoke({"messages": [_tool_call_message()]}, _runtime_config())
    finally:
        for stream in (incoming_send, incoming_receive, outgoing_send, outgoing_receive):
            await stream.aclose()

    tool_message = result["messages"][0]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.status == "error"
    assert "'1' is not of type 'integer'" in str(tool_message.content)
