"""deepagents >=0.7.16 rejects sibling same-path file mutations in one model reply."""

from __future__ import annotations

from importlib.metadata import version
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain_core.messages import AIMessage, ToolMessage
from packaging.version import Version


def _tool_call(call_id: str, name: str, file_path: str) -> dict[str, Any]:
    return {
        "name": name,
        "args": {"file_path": file_path, "old_string": "old", "new_string": "new"},
        "id": call_id,
        "type": "tool_call",
    }


def _request(call: dict[str, Any], siblings: list[dict[str, Any]]) -> MagicMock:
    req = MagicMock()
    req.tool_call = call
    req.state = {"messages": [AIMessage(content="", tool_calls=siblings)]}
    return req


def test_installed_deepagents_includes_same_path_guard() -> None:
    assert Version(version("deepagents")) >= Version("0.7.16")


@pytest.mark.asyncio
async def test_same_path_sibling_edit_is_rejected_before_backend() -> None:
    first = _tool_call("c1", "edit_file", "/report.md")
    second = _tool_call("c2", "edit_file", "/./report.md")
    handler = AsyncMock(return_value=ToolMessage(content="ok", tool_call_id="c2"))

    result = await FilesystemMiddleware().awrap_tool_call(_request(second, [first, second]), handler)

    handler.assert_not_awaited()
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "parallel file mutations" in str(result.content)


@pytest.mark.asyncio
async def test_first_same_path_edit_reaches_backend() -> None:
    first = _tool_call("c1", "edit_file", "/report.md")
    second = _tool_call("c2", "edit_file", "/report.md")
    expected = ToolMessage(content="ok", tool_call_id="c1")
    handler = AsyncMock(return_value=expected)

    result = await FilesystemMiddleware().awrap_tool_call(_request(first, [first, second]), handler)

    handler.assert_awaited_once()
    assert result is expected


@pytest.mark.asyncio
async def test_different_path_edits_still_run() -> None:
    left = _tool_call("c1", "edit_file", "/a.md")
    right = _tool_call("c2", "edit_file", "/b.md")
    expected = ToolMessage(content="ok", tool_call_id="c2")
    handler = AsyncMock(return_value=expected)

    result = await FilesystemMiddleware().awrap_tool_call(_request(right, [left, right]), handler)

    handler.assert_awaited_once()
    assert result is expected
