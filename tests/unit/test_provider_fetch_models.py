"""Unit tests for OpenAI-compatible remote model listing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from octop.infra.agents.providers.probe import fetch_openai_compatible_models


@pytest.fixture(autouse=True)
def _skip_dns_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """SEC-8 added DNS resolution to the probe guard; unit tests stub HTTP."""

    async def _fake_resolve(url: str, *, field: str = "url") -> str:
        return url

    monkeypatch.setattr("octop.infra.utils.ssrf_guard._resolve_validated_ip", _fake_resolve)


def _mock_response(status: int, payload: Any) -> httpx.Response:
    request = httpx.Request("GET", "https://api.example.com/v1/models")
    return httpx.Response(status, json=payload, request=request)


@pytest.mark.asyncio
async def test_fetch_models_parses_openai_list() -> None:
    response = _mock_response(
        200,
        {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini", "owned_by": "system"}]},
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_openai_compatible_models(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
        )

    assert result["ok"] is True
    assert result["models"] == [
        {"id": "gpt-4o", "name": "gpt-4o"},
        {"id": "gpt-4o-mini", "name": "gpt-4o-mini"},
    ]
    mock_client.get.assert_awaited_once()
    args, kwargs = mock_client.get.await_args
    assert args[0] == "https://api.example.com/v1/models"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_fetch_models_defaults_openai_base_url() -> None:
    response = _mock_response(200, {"data": []})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_openai_compatible_models(base_url=None, api_key="sk-test")

    assert result["ok"] is True
    assert result["models"] == []
    assert mock_client.get.await_args.args[0] == "https://api.openai.com/v1/models"


@pytest.mark.asyncio
async def test_fetch_models_rejects_non_openai_payload() -> None:
    response = _mock_response(200, {"models": ["gpt-4o"]})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_openai_compatible_models(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
        )

    assert result["ok"] is False
    assert "OpenAI" in result["error"] or "compatible" in result["error"].lower()


@pytest.mark.asyncio
async def test_fetch_models_auth_error() -> None:
    response = _mock_response(401, {"error": {"message": "invalid key"}})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_openai_compatible_models(
            base_url="https://api.example.com/v1",
            api_key="bad",
        )

    assert result["ok"] is False
    assert "API key" in result["error"]
    assert "401" not in result["error"]


@pytest.mark.asyncio
async def test_fetch_models_insufficient_balance_zh() -> None:
    response = _mock_response(402, {"error": {"message": "Insufficient Balance"}})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_openai_compatible_models(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
            locale="zh",
        )

    assert result["ok"] is False
    assert "余额" in result["error"] or "额度" in result["error"]
    assert "402" not in result["error"]


@pytest.mark.asyncio
async def test_fetch_models_merges_extra_headers() -> None:
    response = _mock_response(200, {"data": [{"id": "m1"}]})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient", return_value=mock_client):
        await fetch_openai_compatible_models(
            base_url="https://api.example.com/v1/",
            api_key="sk-test",
            extra_headers={"X-Custom": "1"},
        )

    headers = mock_client.get.await_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer sk-test"
    assert headers["X-Custom"] == "1"


@pytest.mark.asyncio
async def test_fetch_models_connection_error() -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_openai_compatible_models(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
        )

    assert result["ok"] is False
    assert result["error"]
    # ConnectError string often includes "connection" → timeout_network guidance
    assert "401" not in result["error"]


@pytest.mark.asyncio
async def test_fetch_models_server_error_friendly() -> None:
    response = _mock_response(503, {"error": {"message": "overloaded"}})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_openai_compatible_models(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
            locale="en",
        )

    assert result["ok"] is False
    assert "temporarily unavailable" in result["error"].lower()
    assert "503" not in result["error"]


@pytest.mark.asyncio
async def test_fetch_models_rejects_private_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """SEC-8: the SSRF guard must reject private/loopback draft base_urls."""
    result = await fetch_openai_compatible_models(
        base_url="http://169.254.169.254/v1",
        api_key="sk-secret",
    )
    assert result["ok"] is False
    assert "not allowed" in result["error"] or "https" in result["error"].lower()


@pytest.mark.asyncio
async def test_fetch_models_allows_loopback_base_url_for_local_runtimes() -> None:
    """Loopback is exempt so on-box Ollama/ONNX can still list their models.

    Without the exemption ``GET http://127.0.0.1:11434/v1/models`` is rejected
    by the guard and local installs cannot be configured at all.
    """
    request = httpx.Request("GET", "http://127.0.0.1:11434/v1/models")
    response = httpx.Response(200, json={"data": [{"id": "llama3"}]}, request=request)
    get = AsyncMock(return_value=response)

    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__ = AsyncMock(return_value=SimpleNamespace(get=get))
        client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        result = await fetch_openai_compatible_models(
            base_url="http://127.0.0.1:11434/v1",
            api_key="",
        )

    assert result["ok"] is True
    assert [m["id"] for m in result["models"]] == ["llama3"]


@pytest.mark.asyncio
async def test_fetch_models_rejects_private_rfc1918_base_url() -> None:
    """Private LAN addresses are NOT loopback and must still be guarded.

    The local-runtime exemption is deliberately loopback-only: a LAN address is
    a real internal host, which is what the guard is there to stop.
    """
    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient") as client_cls:
        result = await fetch_openai_compatible_models(
            base_url="https://192.168.1.10:11434/v1",
            api_key="sk-test",
        )

    assert result["ok"] is False
    assert "not allowed" in result["error"]
    client_cls.assert_not_called()
