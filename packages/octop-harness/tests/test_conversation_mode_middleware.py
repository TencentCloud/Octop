"""Tests for turn-scoped Ask / Plan / Craft conversation mode."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.config import var_child_runnable_config
from langgraph.prebuilt.tool_node import ToolCallRequest

from octop_harness.middleware.conversation_mode import (
    ConversationModeMiddleware,
    apply_conversation_mode_to_request,
    is_allowed_plan_path,
    parse_conversation_mode,
)
from octop_harness.request import ChatRequest


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


def test_parse_conversation_mode_defaults_unknown_to_craft() -> None:
    assert parse_conversation_mode("ask") == "ask"
    assert parse_conversation_mode("plan") == "plan"
    assert parse_conversation_mode("craft") == "craft"
    assert parse_conversation_mode(None) == "craft"
    assert parse_conversation_mode("agent") == "craft"


def test_is_allowed_plan_path() -> None:
    assert is_allowed_plan_path("plans/add-ask-plan-modes.md")
    assert is_allowed_plan_path("/plans/add-ask-plan-modes.md")
    assert not is_allowed_plan_path("plans/增加问答.md")
    assert not is_allowed_plan_path("src/foo.md")
    assert not is_allowed_plan_path("plans/../src/x.md")
    assert not is_allowed_plan_path("plans/sub/a.md")
    assert not is_allowed_plan_path("plans/foo.txt")


def test_ask_filters_write_and_keeps_read() -> None:
    request = ModelRequest(
        model=MagicMock(),
        messages=[],
        system_message=SystemMessage(content="base"),
        tools=[
            _tool("read_file"),
            _tool("write_file"),
            _tool("execute"),
            _tool("web_fetch"),
            _tool("cronjob_create"),
        ],
        state={"skills_metadata": [{"name": "demo"}]},
    )
    with _configurable(conversation_mode="ask"):
        out = apply_conversation_mode_to_request(request)
    names = [getattr(t, "name", None) for t in (out.tools or [])]
    assert names == ["read_file", "web_fetch"]
    assert out.state.get("skills_metadata") == []
    assert "Ask mode" in str(out.system_message.content)


def test_ask_allows_host_read_tools() -> None:
    request = ModelRequest(
        model=MagicMock(),
        messages=[],
        tools=[_tool("search_knowledge"), _tool("write_file")],
    )
    with _configurable(
        conversation_mode="ask",
        conversation_mode_extra_read_tools=["search_knowledge"],
    ):
        out = apply_conversation_mode_to_request(request)
    names = [getattr(t, "name", None) for t in (out.tools or [])]
    assert names == ["search_knowledge"]


def test_plan_keeps_write_file_and_blocks_execute() -> None:
    request = ModelRequest(
        model=MagicMock(),
        messages=[],
        tools=[_tool("write_file"), _tool("edit_file"), _tool("execute"), _tool("read_file")],
    )
    with _configurable(conversation_mode="plan"):
        out = apply_conversation_mode_to_request(request)
    names = [getattr(t, "name", None) for t in (out.tools or [])]
    assert names == ["write_file", "edit_file", "read_file"]
    assert "Plan mode" in str(out.system_message.content)


def test_craft_passthrough() -> None:
    tools = [_tool("write_file"), _tool("execute")]
    request = ModelRequest(
        model=MagicMock(),
        messages=[],
        system_message=SystemMessage(content="base"),
        tools=tools,
        state={"skills_metadata": [{"name": "demo"}]},
    )
    with _configurable(conversation_mode="craft"):
        out = apply_conversation_mode_to_request(request)
    assert [getattr(t, "name", None) for t in (out.tools or [])] == ["write_file", "execute"]
    assert out.state.get("skills_metadata") == [{"name": "demo"}]


@pytest.mark.asyncio
async def test_awrap_tool_call_blocks_ask_write() -> None:
    mw = ConversationModeMiddleware()
    request = ToolCallRequest(
        tool_call={"name": "write_file", "args": {"path": "a.md"}, "id": "c1"},
        tool=None,  # type: ignore[arg-type]
        state={},  # type: ignore[arg-type]
        runtime=None,  # type: ignore[arg-type]
    )
    handler = AsyncMock(return_value=ToolMessage(content="ran", tool_call_id="c1"))
    with _configurable(conversation_mode="ask"):
        result = await mw.awrap_tool_call(request, handler)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "write_file" in result.content
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_awrap_tool_call_plan_allows_plans_path() -> None:
    mw = ConversationModeMiddleware()
    request = ToolCallRequest(
        tool_call={
            "name": "write_file",
            "args": {"path": "plans/add-ask-plan-modes.md", "content": "# plan"},
            "id": "c1",
        },
        tool=None,  # type: ignore[arg-type]
        state={},  # type: ignore[arg-type]
        runtime=None,  # type: ignore[arg-type]
    )
    ok = ToolMessage(content="wrote", tool_call_id="c1")
    handler = AsyncMock(return_value=ok)
    with _configurable(conversation_mode="plan"):
        result = await mw.awrap_tool_call(request, handler)
    assert result is ok
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_awrap_tool_call_plan_blocks_other_paths() -> None:
    mw = ConversationModeMiddleware()
    request = ToolCallRequest(
        tool_call={"name": "write_file", "args": {"path": "src/a.py"}, "id": "c1"},
        tool=None,  # type: ignore[arg-type]
        state={},  # type: ignore[arg-type]
        runtime=None,  # type: ignore[arg-type]
    )
    handler = AsyncMock()
    with _configurable(conversation_mode="plan"):
        result = await mw.awrap_tool_call(request, handler)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "plans/" in result.content
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_ask_blocks_skill_path_read() -> None:
    mw = ConversationModeMiddleware()
    request = ToolCallRequest(
        tool_call={"name": "read_file", "args": {"path": "skills/demo/SKILL.md"}, "id": "c1"},
        tool=None,  # type: ignore[arg-type]
        state={},  # type: ignore[arg-type]
        runtime=None,  # type: ignore[arg-type]
    )
    handler = AsyncMock()
    with _configurable(conversation_mode="ask"):
        result = await mw.awrap_tool_call(request, handler)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    handler.assert_not_called()


def test_chat_request_stamps_conversation_mode() -> None:
    cfg = ChatRequest(messages="hi", conversation_mode="ask").to_runnable_config()
    assert cfg["configurable"]["conversation_mode"] == "ask"
    assert cfg["configurable"]["skills"] == []
    assert cfg["configurable"]["mcp_servers"] == []


def test_chat_request_plan_forces_no_mcp_skills() -> None:
    cfg = ChatRequest(
        messages="hi",
        conversation_mode="plan",
        skills=["demo"],
        mcp_servers=["github"],
        mcp_use_default=True,
    ).to_runnable_config()
    assert cfg["configurable"]["conversation_mode"] == "plan"
    assert cfg["configurable"]["skills"] == []
    assert cfg["configurable"]["mcp_servers"] == []
    assert "mcp_use_default" not in cfg["configurable"]


def test_chat_request_craft_leaves_skills() -> None:
    cfg = ChatRequest(messages="hi", conversation_mode="craft", skills=["demo"]).to_runnable_config()
    assert cfg["configurable"]["conversation_mode"] == "craft"
    assert cfg["configurable"]["skills"] == ["demo"]


def test_apply_uses_runtime_config_when_get_config_empty() -> None:
    request = ModelRequest(
        model=MagicMock(),
        messages=[],
        tools=[_tool("write_file"), _tool("read_file")],
    )
    runtime = {"configurable": {"conversation_mode": "ask"}}
    with patch(
        "octop_harness.middleware.conversation_mode.runtime_config",
        return_value=runtime,
    ):
        out = apply_conversation_mode_to_request(request)
    names = [getattr(t, "name", None) for t in (out.tools or [])]
    assert names == ["read_file"]
