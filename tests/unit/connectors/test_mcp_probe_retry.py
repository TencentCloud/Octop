"""Streamable-HTTP MCP probes must survive one transient connection drop.

The SSE probe (``_probe_mcp_sse``) retries once when the upstream closes the
stream during the first ``initialize``; the streamable-HTTP probe shares the
same error classification but used to give up on the first attempt, so a
transient drop was reported as a broken connector.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from octop.infra.connectors import probe

_URL = "https://mcp.notion.example/mcp"


def _install_fake_mcp(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failures: int = 0,
    auth_rejection: bool = False,
) -> list[int]:
    """Patch the streamable-HTTP client and ``ClientSession``; return the attempt log."""

    attempts: list[int] = []

    @asynccontextmanager
    async def fake_client(url: str, headers: Any = None, **kwargs: Any):
        yield (None, None, None)

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            attempts.append(len(attempts) + 1)
            if auth_rejection:
                request = httpx.Request("POST", _URL)
                response = httpx.Response(401, request=request)
                raise httpx.HTTPStatusError("401 Unauthorized", request=request, response=response)
            if len(attempts) <= failures:
                raise McpError(ErrorData(code=0, message="Connection closed"))
            return self

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

        async def initialize(self) -> None:
            return None

        async def list_tools(self) -> Any:
            return SimpleNamespace(tools=[SimpleNamespace(name="read_file", description="read")])

    monkeypatch.setattr("mcp.client.streamable_http.streamablehttp_client", fake_client)
    monkeypatch.setattr("mcp.ClientSession", lambda *args, **kwargs: FakeSession())
    return attempts


async def test_streamable_http_probe_retries_one_transient_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One dropped ``initialize`` must not be reported as a broken connector."""
    attempts = _install_fake_mcp(monkeypatch, failures=1)

    result = await probe.probe_streamable_http_mcp(
        _URL, {"Authorization": "Bearer good"}, kind="notion"
    )

    assert result["ok"] is True
    assert result["tool_count"] == 1
    assert len(attempts) == 2


async def test_streamable_http_probe_stops_after_the_single_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persistent drop is reported after the retry, not retried forever."""
    attempts = _install_fake_mcp(monkeypatch, failures=99)

    result = await probe.probe_streamable_http_mcp(
        _URL, {"Authorization": "Bearer x"}, kind="notion"
    )

    assert result["ok"] is False
    assert result["error_type"] == "connection"
    assert len(attempts) == 2


async def test_streamable_http_probe_does_not_retry_an_auth_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """401 is definitive: a bad key must never be masked by the retry."""
    attempts = _install_fake_mcp(monkeypatch, auth_rejection=True)

    result = await probe.probe_streamable_http_mcp(
        _URL, {"Authorization": "Bearer bad"}, kind="notion"
    )

    assert result["ok"] is False
    assert result["error_type"] == "auth"
    assert len(attempts) == 1
