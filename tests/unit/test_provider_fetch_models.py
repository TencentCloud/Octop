"""Unit tests for OpenAI-compatible remote model listing."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from octop.infra.agents.providers.probe import fetch_openai_compatible_models


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
    assert "401" in result["error"] or "invalid" in result["error"].lower()


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
