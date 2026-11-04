"""Connection probes must consume the complete MCP tool list."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, ListToolsResult, Tool

from octop.infra.connectors import probe

_URL = "https://mcp.example/mcp"
_TRANSPORTS = ("sse", "http", "stdio")


def _page(*names: str, cursor: str | None = None) -> ListToolsResult:
    return ListToolsResult(
        tools=[
            Tool(name=name, description=f"{name} description", inputSchema={}) for name in names
        ],
        nextCursor=cursor,
    )


def _install_session(monkeypatch: pytest.MonkeyPatch, pages: list[Any]) -> list[list[str | None]]:
    calls: list[list[str | None]] = []

    @asynccontextmanager
    async def sse_client(*args: Any, **kwargs: Any):
        assert kwargs["timeout"] == kwargs["sse_read_timeout"] == 20
        yield None, None

    @asynccontextmanager
    async def http_client(*args: Any, **kwargs: Any):
        assert kwargs["timeout"] == kwargs["sse_read_timeout"] == 20
        yield None, None, None

    @asynccontextmanager
    async def stdio_client(*args: Any, **kwargs: Any):
        yield None, None

    class Session:
        async def __aenter__(self):
            self.calls: list[str | None] = []
            calls.append(self.calls)
            return self

        async def __aexit__(self, *args: Any):
            return False

        async def initialize(self):
            return None

        async def list_tools(self, cursor: str | None = None):
            self.calls.append(cursor)
            page = pages[min(len(self.calls) - 1, len(pages) - 1)]
            if callable(page):
                page = page(len(calls))
            if isinstance(page, BaseException):
                raise page
            if page is None:
                await asyncio.Event().wait()
            return page

    monkeypatch.setattr("mcp.ClientSession", lambda *args, **kwargs: Session())
    monkeypatch.setattr("mcp.client.sse.sse_client", sse_client)
    monkeypatch.setattr("mcp.client.streamable_http.streamablehttp_client", http_client)
    monkeypatch.setattr("mcp.client.stdio.stdio_client", stdio_client)
    return calls


async def _probe(transport: str) -> dict[str, Any]:
    if transport == "sse":
        return await probe._probe_mcp_sse(_URL, kind="custom-mcp")
    if transport == "http":
        return await probe.probe_streamable_http_mcp(_URL, {}, kind="custom-mcp")
    return await probe._probe_stdio_mcp({"command": "fake-mcp"})


@pytest.mark.parametrize("transport", _TRANSPORTS)
@pytest.mark.parametrize(
    ("pages", "names", "cursors"),
    [
        ([_page("first", cursor="page-2"), _page("second")], ["first", "second"], [None, "page-2"]),
        ([_page("only")], ["only"], [None]),
        ([_page()], [], [None]),
        ([_page("first", cursor="end"), _page()], ["first"], [None, "end"]),
    ],
    ids=["two-pages", "single-page", "empty", "empty-final-page"],
)
async def test_complete_tool_list(monkeypatch, transport, pages, names, cursors):
    calls = _install_session(monkeypatch, pages)
    result = await _probe(transport)
    assert result == {
        "ok": True,
        "tool_count": len(names),
        "tools": [{"name": name, "description": f"{name} description"} for name in names],
    }
    assert calls == [cursors]


@pytest.mark.parametrize("transport", _TRANSPORTS)
@pytest.mark.parametrize("cursors", [("same", "same"), ("a", "b", "a")])
async def test_repeated_cursor_fails(monkeypatch, transport, cursors):
    calls = _install_session(monkeypatch, [_page("partial", cursor=c) for c in cursors])
    result = await asyncio.wait_for(_probe(transport), timeout=1)
    assert result["ok"] is False
    assert "tools" not in result
    assert all(len(attempt) <= len(cursors) for attempt in calls)
    assert len(calls) <= (1 if transport == "stdio" else 2)


@pytest.mark.parametrize("transport", _TRANSPORTS)
async def test_later_page_error_cannot_report_partial_success(monkeypatch, transport):
    calls = _install_session(monkeypatch, [_page("partial", cursor="next"), ValueError("bad page")])
    result = await _probe(transport)
    assert result["ok"] is False
    assert "tools" not in result
    assert all(attempt == [None, "next"] for attempt in calls)


@pytest.mark.parametrize("transport", ["sse", "http"])
async def test_retry_restarts_listing_without_partial_tools(monkeypatch, transport):
    def second_page(attempt):
        return (
            McpError(ErrorData(code=0, message="Connection closed"))
            if attempt == 1
            else _page("last")
        )

    calls = _install_session(monkeypatch, [_page("first", cursor="next"), second_page])
    result = await _probe(transport)
    assert result["ok"] is True
    assert result["tool_count"] == 2
    assert [tool["name"] for tool in result["tools"]] == ["first", "last"]
    assert calls == [[None, "next"], [None, "next"]]


@pytest.mark.parametrize("transport", ["sse", "http"])
@pytest.mark.parametrize("status", [401, 403])
async def test_later_page_auth_rejection_is_not_retried(monkeypatch, transport, status):
    request = httpx.Request("POST", _URL)
    rejection = httpx.HTTPStatusError(
        "auth rejected", request=request, response=httpx.Response(status, request=request)
    )
    calls = _install_session(monkeypatch, [_page("partial", cursor="next"), rejection])
    result = await _probe(transport)
    assert result["ok"] is False
    assert result["error_type"] == "auth"
    assert result["status_code"] == status
    assert calls == [[None, "next"]]


@pytest.mark.parametrize("transport", _TRANSPORTS)
async def test_pagination_stays_within_probe_timeout(monkeypatch, transport):
    calls = _install_session(monkeypatch, [_page("partial", cursor="next"), None])
    real_timeout = asyncio.timeout
    deadlines: list[float] = []

    def short_timeout(delay):
        deadlines.append(delay)
        return real_timeout(0.01)

    monkeypatch.setattr(probe.asyncio, "timeout", short_timeout)
    result = await asyncio.wait_for(_probe(transport), timeout=1)
    assert result["ok"] is False
    assert "tools" not in result
    assert result["error"]
    assert deadlines == ([25] if transport == "stdio" else [20, 20])
    assert all(attempt == [None, "next"] for attempt in calls)


@pytest.mark.parametrize("transport", _TRANSPORTS)
async def test_pagination_propagates_cancellation(monkeypatch, transport):
    calls = _install_session(
        monkeypatch, [_page("partial", cursor="next"), asyncio.CancelledError()]
    )
    with pytest.raises(asyncio.CancelledError):
        await _probe(transport)
    assert calls == [[None, "next"]]
