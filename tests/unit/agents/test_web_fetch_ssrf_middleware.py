"""Tests for the web-fetch SSRF middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from langgraph.prebuilt.tool_node import ToolCallRequest

from octop.infra.agents.middleware import web_fetch_ssrf
from octop.infra.utils.ssrf_guard import UnsafeOutboundUrl


def _request(name: str, args: dict[str, object]) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": "call-1"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_web_fetch_blocks_private_ip() -> None:
    handler = AsyncMock(return_value=object())
    request = _request(
        "web_fetch",
        {"url": "http://10.182.12.254:8080/portal/index_phone.jsp", "timeout": 20},
    )

    result = await web_fetch_ssrf.WebFetchSSRFGuardMiddleware().awrap_tool_call(request, handler)

    handler.assert_not_awaited()
    assert getattr(result, "status", None) == "error"
    assert "private or reserved" in str(result.content)


@pytest.mark.asyncio
async def test_web_fetch_blocks_private_dns_result(monkeypatch) -> None:
    monkeypatch.setattr(
        web_fetch_ssrf,
        "validate_http_url_resolved",
        AsyncMock(
            side_effect=UnsafeOutboundUrl("private or reserved IP addresses are not allowed")
        ),
    )
    handler = AsyncMock(return_value=object())
    request = _request("web_fetch", {"url": "https://public.example/page"})

    result = await web_fetch_ssrf.WebFetchSSRFGuardMiddleware().awrap_tool_call(request, handler)

    handler.assert_not_awaited()
    assert getattr(result, "status", None) == "error"
    assert "private or reserved" in str(result.content)


@pytest.mark.asyncio
async def test_web_fetch_allows_validated_public_url(monkeypatch) -> None:
    validate = AsyncMock(return_value="https://public.example/page")
    monkeypatch.setattr(web_fetch_ssrf, "validate_http_url_resolved", validate)
    handler = AsyncMock(return_value=object())
    request = _request("web_fetch", {"url": "https://public.example/page"})

    await web_fetch_ssrf.WebFetchSSRFGuardMiddleware().awrap_tool_call(request, handler)

    validate.assert_awaited_once_with("https://public.example/page", field="url")
    handler.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_non_web_fetch_tool_is_unchanged() -> None:
    handler = AsyncMock(return_value=object())
    request = _request("read_file", {"path": "notes.txt"})

    await web_fetch_ssrf.WebFetchSSRFGuardMiddleware().awrap_tool_call(request, handler)

    handler.assert_awaited_once_with(request)
