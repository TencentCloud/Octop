from __future__ import annotations

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from octop.infra.agents.middleware.disabled_tools import DisabledToolsMiddleware


def request(name: str) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": {"path": "answer.txt"}, "id": "call-1"},
        tool=None,
        state={},
        runtime=None,
    )


def test_disabled_tool_is_rejected_before_handler() -> None:
    middleware = DisabledToolsMiddleware(["write_file"])
    called = False

    def handler(_request: ToolCallRequest) -> ToolMessage:
        nonlocal called
        called = True
        return ToolMessage(content="side effect", tool_call_id="call-1")

    result = middleware.wrap_tool_call(request("write_file"), handler)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "disabled" in str(result.content)
    assert not called


def test_namespaced_disabled_tool_uses_leaf_name() -> None:
    middleware = DisabledToolsMiddleware(["write_file"])
    result = middleware.wrap_tool_call(request("filesystem/write_file"), lambda _: pytest.fail())
    assert isinstance(result, ToolMessage)
    assert result.status == "error"


def test_allowed_tool_reaches_handler() -> None:
    middleware = DisabledToolsMiddleware(["write_file"])
    called = False

    def handler(_request: ToolCallRequest) -> ToolMessage:
        nonlocal called
        called = True
        return ToolMessage(content="ok", tool_call_id="call-1")

    result = middleware.wrap_tool_call(request("read_file"), handler)
    assert called
    assert result.content == "ok"


@pytest.mark.asyncio
async def test_disabled_tool_is_rejected_async() -> None:
    middleware = DisabledToolsMiddleware(["execute"])
    called = False

    async def handler(_request: ToolCallRequest) -> ToolMessage:
        nonlocal called
        called = True
        return ToolMessage(content="side effect", tool_call_id="call-1")

    result = await middleware.awrap_tool_call(request("execute"), handler)
    assert result.status == "error"
    assert not called
