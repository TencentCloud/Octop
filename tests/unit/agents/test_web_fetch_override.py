"""Unit tests for the DeepSeek ``web_fetch`` override middleware."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolNode
from octop_harness.builtin.tools import web_fetch as builtin_web_fetch

from octop.infra.agents.middleware.web_fetch_override import (
    WebFetchOverrideMiddleware,
    _is_builtin_web_fetch,
)


class _FakeRequest:
    def __init__(self, tools: list[Any]) -> None:
        self.tools = tools

    def override(self, *, tools: list[Any]) -> _FakeRequest:
        return _FakeRequest(tools)


async def _deepseek_fetch(url: str) -> str:
    return url


def _replacement_tool() -> StructuredTool:
    return StructuredTool.from_function(
        coroutine=_deepseek_fetch,
        name="web_fetch",
        description="DeepSeek-backed fetch",
    )


def test_builtin_web_fetch_identity() -> None:
    replacement = _replacement_tool()
    assert _is_builtin_web_fetch(builtin_web_fetch) is True
    assert _is_builtin_web_fetch(replacement) is False
    assert _is_builtin_web_fetch({"name": "web_fetch"}) is False


def test_middleware_hides_builtin_and_keeps_replacement() -> None:
    replacement = _replacement_tool()
    middleware = WebFetchOverrideMiddleware()
    request = _FakeRequest([builtin_web_fetch, replacement])

    filtered = middleware._apply(request)  # type: ignore[arg-type]

    assert filtered.tools == [replacement]


def test_tool_node_executes_the_replacement_for_the_shared_name() -> None:
    """Later-mounted tools win in ToolNode, so tool calls run DeepSeek's fetch."""
    replacement = _replacement_tool()
    node = ToolNode([builtin_web_fetch, replacement])
    assert node.tools_by_name["web_fetch"] is replacement


def test_middleware_is_noop_when_builtin_absent() -> None:
    replacement = _replacement_tool()
    middleware = WebFetchOverrideMiddleware()
    request = _FakeRequest([replacement])

    assert middleware._apply(request) is request  # type: ignore[arg-type]
