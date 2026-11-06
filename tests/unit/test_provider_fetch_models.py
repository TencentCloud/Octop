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


@pytest.mark.parametrize(
    ("provider_name", "expected_ids"),
    [
        ("tencent-hy-token-plan", {"hy4", "hy3", "hy3-preview"}),
        ("Tencent Cloud Hy Token Plan", {"hy4", "hy3", "hy3-preview"}),
        ("tencent-token-plan", {"hy4", "glm-5"}),
        ("Tencent Cloud Token Plan", {"hy4", "glm-5"}),
    ],
)
async def test_shared_plan_url_uses_selected_catalog(
    provider_name: str, expected_ids: set[str]
) -> None:
    base_url = "https://api.lkeap.cloud.tencent.com/plan/v3"
    presets = [
        {
            "id": "tencent-token-plan",
            "name": "Tencent Cloud Token Plan",
            "base_url": base_url,
            "models": [{"id": "hy4"}, {"id": "glm-5"}],
        },
        {
            "id": "tencent-hy-token-plan",
            "name": "Tencent Cloud Hy Token Plan",
            "base_url": base_url,
            "models": [{"id": "hy4"}, {"id": "hy3"}, {"id": "hy3-preview"}],
        },
    ]
    with (
        patch("octop.infra.agents.providers.probe.load_provider_presets", return_value=presets),
        patch("octop.infra.agents.providers.probe.httpx.AsyncClient") as remote,
    ):
        result = await fetch_openai_compatible_models(
            base_url=f"{base_url}/",
            api_key="test-key",
            provider_name=provider_name,
        )
    assert result["ok"] is True
    assert {model["id"] for model in result["models"]} == expected_ids
    remote.assert_not_called()


@pytest.mark.parametrize(
    ("provider_name", "base_url"),
    [
        ("Custom provider", "https://api.lkeap.cloud.tencent.com/plan/v3"),
        ("Tencent Cloud Hy Token Plan", "https://proxy.example.com/v1"),
        ("tencent-tokenhub", "https://tokenhub.tencentmaas.com/v1"),
        ("tencent-hai", "https://api.model.haihub.cn/v1"),
    ],
)
async def test_other_provider_or_url_keeps_remote_discovery(
    provider_name: str, base_url: str
) -> None:
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.return_value = _mock_response(200, {"data": [{"id": "remote-model"}]})
    with patch("octop.infra.agents.providers.probe.httpx.AsyncClient", return_value=client):
        result = await fetch_openai_compatible_models(
            base_url=base_url, api_key="test-key", provider_name=provider_name
        )
    assert result == {"ok": True, "models": [{"id": "remote-model", "name": "remote-model"}]}
    assert client.get.await_args.args[0] == f"{base_url}/models"


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


_KVMEM_REASONING = {
    "supported": True,
    "toggle": True,
    "default_mode": "disabled",
    "efforts": ["low", "medium", "xhigh"],
    "default_effort": None,
    "effort_type": "enum",
    "adapter": "llamacpp",
    "budget_tokens": 1024,
}


@pytest.mark.asyncio
async def test_fetch_models_maps_kvmem_model_metadata() -> None:
    response = _mock_response(
        200,
        {
            "object": "list",
            "data": [
                {
                    "id": "m",
                    "name": "m",
                    "object": "model",
                    "status": {"value": "loaded"},
                    "context_length": 8192,
                    "max_output_tokens": 2048,
                    "api_mode": "chat_completions",
                    "input": ["text"],
                    "kvmem": {
                        "generation_limit": 4096,
                        "capabilities": {
                            "tools": True,
                            "thinking": True,
                            "vision": False,
                        },
                        "reasoning": _KVMEM_REASONING,
                    },
                },
                {"id": "legacy-model"},
            ],
        },
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
        {"id": "legacy-model", "name": "legacy-model"},
        {
            "id": "m",
            "name": "m",
            "context_window": 8192,
            "max_tokens": 2048,
            "input": ["text"],
            "api_mode": "chat_completions",
            "reasoning": True,
            "reasoning_config": _KVMEM_REASONING,
        },
    ]


@pytest.mark.asyncio
async def test_fetch_models_skips_invalid_kvmem_fields() -> None:
    response = _mock_response(
        200,
        {
            "data": [
                {
                    "id": "bad-types",
                    "context_length": "8192",
                    "max_output_tokens": True,
                    "input": ["text", 1],
                    "api_mode": "",
                    "kvmem": {"reasoning": "yes"},
                },
                {
                    "id": "bad-reasoning",
                    "context_length": -1,
                    "max_output_tokens": 0,
                    "input": "text",
                    "api_mode": 42,
                    "kvmem": {"reasoning": ["supported"]},
                },
                {"id": "kvmem-not-dict", "kvmem": "broken", "context_length": 4096},
            ]
        },
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
        {"id": "bad-reasoning", "name": "bad-reasoning"},
        {"id": "bad-types", "name": "bad-types"},
        {"id": "kvmem-not-dict", "name": "kvmem-not-dict"},
    ]


@pytest.mark.asyncio
async def test_fetch_models_invalid_kvmem_does_not_raise() -> None:
    response = _mock_response(
        200,
        {
            "data": [
                {
                    "id": "m",
                    "kvmem": {"reasoning": {"supported": "yes", "efforts": "low"}},
                    "context_length": [8192],
                },
            ]
        },
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
    assert result["models"] == [{"id": "m", "name": "m"}]
