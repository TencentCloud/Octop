"""MCP connection probes must page through a paginated ``tools/list`` (#2298).

A server that returns ``nextCursor`` from ``tools/list`` is only partially
probed by a single call, so the reported tool list and ``tool_count`` silently
omit later pages. The SSE, Streamable-HTTP and stdio probes must keep calling
``list_tools`` with each cursor until the server stops returning one.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from mcp.types import ListToolsResult, Tool

from octop.infra.connectors import probe

_URL = "https://mcp.example/mcp"


class _PaginatedSession:
    """``ClientSession`` fake serving a fixed list of pages."""

    def __init__(self, pages: list[tuple[list[str], str | None]]) -> None:
        self._pages = pages
        self._idx = 0
        self.cursors_seen: list[str | None] = []

    async def __aenter__(self) -> "_PaginatedSession":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def initialize(self) -> None:
        return None

    async def list_tools(self, cursor: str | None = None, **kwargs: Any) -> ListToolsResult:
        self.cursors_seen.append(cursor)
        names, nxt = self._pages[self._idx]
        self._idx += 1
        tools = [
            Tool(name=name, description=f"desc {name}", inputSchema={"type": "object"})
            for name in names
        ]
        return ListToolsResult(tools=tools, nextCursor=nxt)


class _InfiniteCursorSession:
    """``ClientSession`` fake that always returns a non-empty cursor (defense)."""

    def __init__(self) -> None:
        self.calls = 0

    async def __aenter__(self) -> "_InfiniteCursorSession":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def initialize(self) -> None:
        return None

    async def list_tools(self, cursor: str | None = None, **kwargs: Any) -> ListToolsResult:
        self.calls += 1
        return ListToolsResult(
            tools=[
                Tool(
                    name=f"tool-{self.calls}",
                    description="",
                    inputSchema={"type": "object"},
                )
            ],
            nextCursor="keep-going",
        )


@asynccontextmanager
async def _fake_transport(arity: int, *args: Any, **kwargs: Any):
    # sse/stdio unpack (read, write); streamable_http unpacks (read, write, _id).
    yield tuple(None for _ in range(arity))


def _install(monkeypatch: pytest.MonkeyPatch, session: Any, *, transport: str) -> None:
    if transport == "sse":
        fake = lambda *a, **k: _fake_transport(2, *a, **k)
        monkeypatch.setattr("mcp.client.sse.sse_client", fake)
    elif transport == "streamable_http":
        fake = lambda *a, **k: _fake_transport(3, *a, **k)
        monkeypatch.setattr(
            "mcp.client.streamable_http.streamablehttp_client", fake
        )
    elif transport == "stdio":
        fake = lambda *a, **k: _fake_transport(2, *a, **k)
        monkeypatch.setattr("mcp.client.stdio.stdio_client", fake)
    else:
        raise AssertionError(f"unknown transport: {transport}")
    monkeypatch.setattr("mcp.ClientSession", lambda *a, **k: session)


async def test_sse_probe_pages_through_tools_list(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _PaginatedSession([(["first_tool"], "page-2"), (["second_tool"], None)])
    _install(monkeypatch, session, transport="sse")

    result = await probe._probe_mcp_sse(_URL, {}, kind="custom-mcp")

    assert result["ok"] is True
    assert result["tool_count"] == 2
    assert {t["name"] for t in result["tools"]} == {"first_tool", "second_tool"}
    assert session.cursors_seen == [None, "page-2"]


async def test_streamable_http_probe_pages_through_tools_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _PaginatedSession([(["first_tool"], "page-2"), (["second_tool"], None)])
    _install(monkeypatch, session, transport="streamable_http")

    result = await probe.probe_streamable_http_mcp(_URL, {}, kind="custom-mcp")

    assert result["ok"] is True
    assert result["tool_count"] == 2
    assert {t["name"] for t in result["tools"]} == {"first_tool", "second_tool"}
    assert session.cursors_seen == [None, "page-2"]


async def test_stdio_probe_pages_through_tools_list(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _PaginatedSession([(["first_tool"], "page-2"), (["second_tool"], None)])
    _install(monkeypatch, session, transport="stdio")

    result = await probe._probe_stdio_mcp({"command": "fake", "args": []})

    assert result["ok"] is True
    assert result["tool_count"] == 2
    assert {t["name"] for t in result["tools"]} == {"first_tool", "second_tool"}
    assert session.cursors_seen == [None, "page-2"]


async def test_single_page_without_cursor_is_not_double_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _PaginatedSession([(["only_tool"], None)])
    _install(monkeypatch, session, transport="streamable_http")

    result = await probe.probe_streamable_http_mcp(_URL, {}, kind="custom-mcp")

    assert result["ok"] is True
    assert result["tool_count"] == 1
    assert session.cursors_seen == [None]


async def test_perpetual_cursor_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _InfiniteCursorSession()
    _install(monkeypatch, session, transport="streamable_http")

    result = await probe.probe_streamable_http_mcp(_URL, {}, kind="custom-mcp")

    assert result["ok"] is True
    assert session.calls == probe._MAX_TOOL_PAGES
    assert result["tool_count"] == probe._MAX_TOOL_PAGES
