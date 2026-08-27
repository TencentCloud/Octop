"""Unit tests for provider connectivity probe helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from octop.infra.agents.providers.probe import build_probe_chat_model as _build_chat_model
from octop.infra.agents.providers.probe import probe_provider_row


def test_build_chat_model_includes_provider_id_and_model_name() -> None:
    row = SimpleNamespace(
        name="HAI",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        get_models=lambda: [{"id": "MiniMax-M2.7", "name": "MiniMax-M2.7"}],
    )

    with patch("harness_agent.llm.factory.build_chat_model") as mock_build:
        mock_build.return_value = object()
        _build_chat_model(row, model_id="MiniMax-M2.7")

    provider, model = mock_build.call_args[0]
    assert provider.id == "HAI"
    assert provider.name == "HAI"
    assert model.id == "MiniMax-M2.7"
    assert model.name == "MiniMax-M2.7"


def test_build_chat_model_preserves_mixed_protocol_model_metadata() -> None:
    row = SimpleNamespace(
        name="opencode-go",
        kind="openai",
        base_url="https://opencode.ai/zen/go/v1",
        api_key="sk-test",
        get_models=lambda: [
            {
                "id": "qwen3.8-max",
                "name": "Qwen 3.8 Max",
                "wire_api": "anthropic_messages",
                "endpoint_base_url": "https://opencode.ai/zen/go",
                "max_tokens": 131_072,
            }
        ],
    )

    with patch("harness_agent.llm.factory.build_chat_model") as mock_build:
        mock_build.return_value = object()
        _build_chat_model(row, model_id="qwen3.8-max")

    _provider, model = mock_build.call_args[0]
    assert model.wire_api == "anthropic_messages"
    assert model.endpoint_base_url == "https://opencode.ai/zen/go"
    assert model.max_output_tokens == 131_072


def _embedding_row(**overrides: Any) -> SimpleNamespace:
    models = overrides.pop(
        "models",
        [{"id": "text-embedding-3-small", "name": "embed", "embedding": True}],
    )
    data = {
        "name": "openai",
        "kind": "openai",
        "base_url": "https://api.example.com/v1/",
        "api_key": "sk-test",
        "extra_json": None,
        "get_models": lambda: models,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _mock_async_client(*, post: AsyncMock) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.post = post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_embedding_probe_posts_embeddings_endpoint() -> None:
    request = httpx.Request("POST", "https://api.example.com/v1/embeddings")
    response = httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]}, request=request)
    post = AsyncMock(return_value=response)
    with (
        patch(
            "octop.infra.agents.providers.probe.httpx.AsyncClient",
            return_value=_mock_async_client(post=post),
        ),
        patch("octop.infra.agents.providers.probe.build_probe_chat_model") as chat,
    ):
        result = await probe_provider_row(_embedding_row(), model_id="text-embedding-3-small")

    assert result["ok"] is True
    assert isinstance(result["latency_ms"], int)
    chat.assert_not_called()
    args, kwargs = post.await_args
    assert args[0] == "https://api.example.com/v1/embeddings"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert kwargs["json"] == {"model": "text-embedding-3-small", "input": ["ping"]}


@pytest.mark.asyncio
async def test_embedding_probe_honors_explicit_flag_without_saved_model() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    response = httpx.Response(200, json={"data": [{"embedding": [1.0]}]}, request=request)
    post = AsyncMock(return_value=response)
    row = SimpleNamespace(
        name="draft",
        kind="openai",
        base_url=None,
        api_key="sk-test",
        extra_json=None,
        get_models=lambda: [{"id": "embed-1", "name": "embed-1"}],
    )
    with patch(
        "octop.infra.agents.providers.probe.httpx.AsyncClient",
        return_value=_mock_async_client(post=post),
    ):
        result = await probe_provider_row(row, model_id="embed-1", embedding=True)

    assert result["ok"] is True
    assert post.await_args.args[0] == "https://api.openai.com/v1/embeddings"


@pytest.mark.asyncio
async def test_embedding_probe_reports_http_error() -> None:
    request = httpx.Request("POST", "https://api.example.com/v1/embeddings")
    response = httpx.Response(401, json={"error": {"message": "bad key"}}, request=request)
    post = AsyncMock(return_value=response)
    with patch(
        "octop.infra.agents.providers.probe.httpx.AsyncClient",
        return_value=_mock_async_client(post=post),
    ):
        result = await probe_provider_row(_embedding_row())

    assert result["ok"] is False
    assert "401" in result["error"]
    assert "POST https://api.example.com/v1/embeddings" in result["error"]


@pytest.mark.asyncio
async def test_embedding_probe_reports_empty_404_with_url() -> None:
    request = httpx.Request("POST", "https://api.model.haihub.cn/v1/embeddings")
    response = httpx.Response(404, text="", request=request)
    post = AsyncMock(return_value=response)
    row = _embedding_row(
        name="HAI",
        base_url="https://api.model.haihub.cn/v1",
        models=[{"id": "bge-large-zh-v1.5", "name": "bge", "embedding": True}],
    )
    with patch(
        "octop.infra.agents.providers.probe.httpx.AsyncClient",
        return_value=_mock_async_client(post=post),
    ):
        result = await probe_provider_row(row, model_id="bge-large-zh-v1.5")

    assert result["ok"] is False
    assert result["error"] == "HTTP 404 POST https://api.model.haihub.cn/v1/embeddings"


@pytest.mark.asyncio
async def test_chat_probe_skips_embeddings_endpoint() -> None:
    row = SimpleNamespace(
        name="HAI",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        extra_json=None,
        get_models=lambda: [{"id": "gpt-4o-mini", "name": "gpt-4o-mini"}],
    )
    fake = AsyncMock()
    fake.ainvoke = AsyncMock(return_value=SimpleNamespace(content="pong"))
    with (
        patch(
            "octop.infra.agents.providers.probe.build_probe_chat_model",
            return_value=fake,
        ),
        patch("octop.infra.agents.providers.probe.httpx.AsyncClient") as client,
    ):
        result = await probe_provider_row(row, model_id="gpt-4o-mini")

    assert result["ok"] is True
    client.assert_not_called()
    fake.ainvoke.assert_awaited_once()
