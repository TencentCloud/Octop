"""Tests for stable parent/subagent model-facing tool ordering."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.tools import StructuredTool

from octop_harness.middleware.tool_order import TaskToolLastMiddleware, move_tools_to_end


def _tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def test_move_task_to_end_preserves_shared_tool_order() -> None:
    tools = [_tool("write_todos"), _tool("task"), _tool("current_time"), _tool("web_fetch")]

    reordered = move_tools_to_end(tools, frozenset({"task"}))

    assert [tool.name for tool in reordered] == [
        "write_todos",
        "current_time",
        "web_fetch",
        "task",
    ]
    assert reordered[0] is tools[0]
    assert reordered[-1] is tools[1]


def test_move_tools_supports_openai_schema_dicts() -> None:
    tools = [
        {"type": "function", "function": {"name": "task"}},
        {"type": "function", "function": {"name": "lookup"}},
    ]

    reordered = move_tools_to_end(tools, frozenset({"task"}))

    assert reordered == [tools[1], tools[0]]


def test_middleware_overrides_only_model_request_tools() -> None:
    shared = StructuredTool.from_function(lambda: "ok", name="shared", description="shared")
    task = StructuredTool.from_function(lambda: "ok", name="task", description="task")
    request = MagicMock()
    request.tools = [task, shared]
    overridden = MagicMock()
    request.override.return_value = overridden
    handler = MagicMock(return_value="response")

    result = TaskToolLastMiddleware().wrap_model_call(request, handler)

    request.override.assert_called_once_with(tools=[shared, task])
    handler.assert_called_once_with(overridden)
    assert result == "response"


@pytest.mark.asyncio
async def test_async_middleware_keeps_already_stable_order() -> None:
    shared = _tool("shared")
    task = _tool("task")
    request = MagicMock()
    request.tools = [shared, task]
    handler = MagicMock()

    async def async_handler(value: object) -> str:
        handler(value)
        return "response"

    result = await TaskToolLastMiddleware().awrap_model_call(request, async_handler)

    request.override.assert_not_called()
    handler.assert_called_once_with(request)
    assert result == "response"
