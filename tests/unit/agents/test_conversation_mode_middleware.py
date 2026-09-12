"""Unit tests for ConversationModeMiddleware (#616)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.config import var_child_runnable_config
from langgraph.prebuilt.tool_node import ToolCallRequest

from octop.infra.agents.middleware.conversation_mode import (
    ConversationModeMiddleware,
    apply_conversation_mode_to_request,
)


@contextmanager
def _configurable(**kwargs: object):
    token = var_child_runnable_config.set({"configurable": kwargs})
    try:
        yield
    finally:
        var_child_runnable_config.reset(token)


def _tool(name: str) -> StructuredTool:
    return StructuredTool.from_function(
        func=lambda: "x",
        name=name,
        description=name,
    )


def test_ask_filters_mutating_tools_and_keeps_read_tools() -> None:
    request = ModelRequest(
        model=MagicMock(),
        messages=[],
        system_message=SystemMessage(content="base"),
        tools=[_tool("read_file"), _tool("write_file"), _tool("execute"), _tool("write_todos")],
    )
    with _configurable(
        conversation_mode="ask",
        conversation_mode_hint="ASK_HINT",
    ):
        out = apply_conversation_mode_to_request(request)
    names = [getattr(t, "name", None) for t in (out.tools or [])]
    assert names == ["read_file"]
    assert out.system_message is not None
    assert "base" in str(out.system_message.content)
    assert "ASK_HINT" in str(out.system_message.content)


def test_plan_allows_write_todos_and_blocks_execute() -> None:
    request = ModelRequest(
        model=MagicMock(),
        messages=[],
        tools=[_tool("write_todos"), _tool("execute"), _tool("edit_file")],
    )
    with _configurable(conversation_mode="plan", conversation_mode_hint="PLAN_HINT"):
        out = apply_conversation_mode_to_request(request)
    names = [getattr(t, "name", None) for t in (out.tools or [])]
    assert names == ["write_todos"]
    assert "PLAN_HINT" in str(out.system_message.content)


def test_craft_is_passthrough_for_tools() -> None:
    tools = [_tool("write_file"), _tool("execute")]
    request = ModelRequest(
        model=MagicMock(),
        messages=[],
        system_message=SystemMessage(content="base"),
        tools=tools,
    )
    with _configurable(conversation_mode="craft", conversation_mode_hint="CRAFT_HINT"):
        out = apply_conversation_mode_to_request(request)
    assert [getattr(t, "name", None) for t in (out.tools or [])] == ["write_file", "execute"]
    assert "CRAFT_HINT" in str(out.system_message.content)


def test_hint_not_duplicated_on_repeat() -> None:
    request = ModelRequest(
        model=MagicMock(),
        messages=[],
        system_message=SystemMessage(content="base\n\nHINT"),
        tools=[],
    )
    with _configurable(conversation_mode="ask", conversation_mode_hint="HINT"):
        out = apply_conversation_mode_to_request(request)
    assert str(out.system_message.content).count("HINT") == 1


@pytest.mark.asyncio
async def test_awrap_tool_call_blocks_ask_denylist() -> None:
    mw = ConversationModeMiddleware()
    request = ToolCallRequest(
        tool_call={"name": "execute", "args": {}, "id": "c1"},
        tool=None,  # type: ignore[arg-type]
        state={},  # type: ignore[arg-type]
        runtime=None,  # type: ignore[arg-type]
    )
    handler = AsyncMock(return_value=ToolMessage(content="ran", tool_call_id="c1"))
    with _configurable(conversation_mode="ask", locale="en"):
        result = await mw.awrap_tool_call(request, handler)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "execute" in result.content
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_awrap_tool_call_allows_craft() -> None:
    mw = ConversationModeMiddleware()
    request = ToolCallRequest(
        tool_call={"name": "execute", "args": {}, "id": "c1"},
        tool=None,  # type: ignore[arg-type]
        state={},  # type: ignore[arg-type]
        runtime=None,  # type: ignore[arg-type]
    )
    ok = ToolMessage(content="ran", tool_call_id="c1")
    handler = AsyncMock(return_value=ok)
    with _configurable(conversation_mode="craft"):
        result = await mw.awrap_tool_call(request, handler)
    assert result is ok
    handler.assert_awaited_once()
