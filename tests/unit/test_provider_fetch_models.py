"""Unit tests for remote model listing (OpenAI-compatible and Anthropic)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from octop.infra.agents.providers.probe import (
    fetch_anthropic_models,
    fetch_openai_compatible_models,
)


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


def _anthropic_client(*responses: httpx.Response) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=list(responses))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_fetch_anthropic_models_uses_native_api() -> None:
    response = _mock_response(
        200,
        {
            "data": [
                {"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5", "type": "model"},
                {"id": "claude-haiku-5-5", "display_name": "", "type": "model"},
            ],
            "has_more": False,
            "first_id": "claude-opus-5-5",
            "last_id": "claude-haiku-5-5",
        },
    )
    mock_client = _anthropic_client(response)

    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_anthropic_models(
            base_url="https://api.anthropic.com/v1",
            api_key="sk-ant-test",
        )

    assert result == {
        "ok": True,
        "models": [
            {"id": "claude-haiku-5-5", "name": "claude-haiku-5-5"},
            {"id": "claude-opus-5-5", "name": "Claude Opus 5.5"},
        ],
    }
    args, kwargs = mock_client.get.await_args
    assert args[0] == "https://api.anthropic.com/v1/models"
    assert kwargs["headers"]["x-api-key"] == "sk-ant-test"
    assert kwargs["headers"]["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in kwargs["headers"]


@pytest.mark.asyncio
async def test_fetch_anthropic_models_defaults_base_url_and_paginates() -> None:
    page1 = _mock_response(200, {"data": [{"id": "m1"}], "has_more": True, "last_id": "m1"})
    page2 = _mock_response(200, {"data": [{"id": "m2"}], "has_more": False, "last_id": "m2"})
    mock_client = _anthropic_client(page1, page2)

    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_anthropic_models(base_url=None, api_key="sk-ant-test")

    assert [m["id"] for m in result["models"]] == ["m1", "m2"]
    calls = mock_client.get.await_args_list
    assert calls[0].args[0] == "https://api.anthropic.com/v1/models"
    assert "after_id" not in calls[0].kwargs["params"]
    assert calls[1].kwargs["params"]["after_id"] == "m1"


@pytest.mark.asyncio
async def test_fetch_anthropic_models_auth_error() -> None:
    response = _mock_response(
        401,
        {
            "type": "error",
            "error": {"type": "authentication_error", "message": "invalid x-api-key"},
        },
    )
    mock_client = _anthropic_client(response)

    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_anthropic_models(base_url="https://api.anthropic.com", api_key="bad")

    assert result["ok"] is False
    assert result["error"]
