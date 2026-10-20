"""Memory request policy against real SDK serialization, without network."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.llm.factory import ChatModelFactory
from octop_harness.memory.llm_client import HarnessAgentLLMClient


def _factory() -> ChatModelFactory:
    return ChatModelFactory(
        [
            ProviderConfig(
                id="local", base_url="https://local.example/v1", api_key="test", models=[ModelConfig(id="Qwen3")]
            ),
            ProviderConfig(
                id="other", base_url="https://other.example/v1", api_key="test", models=[ModelConfig(id="gpt-4.1")]
            ),
        ]
    )


def _response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        json={
            "id": "audit",
            "object": "chat.completion",
            "created": 0,
            "model": "test",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        },
    )


@pytest.mark.parametrize("retries", [0, 1, 2])
def test_timeout_attempts_do_not_multiply_sdk_retries(monkeypatch: pytest.MonkeyPatch, retries: int) -> None:
    calls: list[httpx.Request] = []
    delays: list[float] = []

    def send(self: httpx.Client, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        calls.append(request)
        if len(calls) <= retries:
            raise httpx.ReadTimeout("probe timeout", request=request)
        return _response(request)

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr("octop_harness.memory.llm_client.time.sleep", delays.append)
    factory = _factory()
    chat = factory.get_chat_model("local/Qwen3")
    client = HarnessAgentLLMClient(factory, default_model="local/Qwen3", max_retries=retries, retry_backoff_s=0.5)
    try:
        assert client.call_llm("probe", max_tokens=1024) == "ok"
        assert len(calls) == retries + 1
        assert delays == [0.5 * 2**i for i in range(retries)]
        assert all(json.loads(r.content)["max_completion_tokens"] == 1024 for r in calls)
        assert all("max_retries" not in json.loads(r.content) for r in calls)
        assert factory.get_chat_model("local/Qwen3") is chat
        assert chat.root_client.max_retries == 2
        assert factory.get_chat_model("local/Qwen3", max_retries=0).root_client.max_retries == 0
    finally:
        factory.close()


def test_fallback_drops_primary_vendor_options(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    def send(self: httpx.Client, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        requests.append(request)
        if request.url.host == "local.example":
            return httpx.Response(
                400, request=request, json={"error": {"message": "model unavailable", "type": "invalid_request_error"}}
            )
        return _response(request)

    monkeypatch.setattr(httpx.Client, "send", send)
    factory = _factory()
    client = HarnessAgentLLMClient(
        factory,
        aux_model="local/Qwen3",
        default_model="other/gpt-4.1",
        thinking="off",
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        max_retries=2,
    )
    try:
        assert client.call_llm("probe", max_tokens=512) == "ok"
        assert len(requests) == 2  # permanent 400 is not retried
        assert "chat_template_kwargs" in json.loads(requests[0].content)
        assert "chat_template_kwargs" not in json.loads(requests[1].content)
        assert json.loads(requests[1].content)["max_completion_tokens"] == 512
    finally:
        factory.close()


def test_retry_policy_roundtrip_and_validation() -> None:
    config = HarnessAgentConfig(name="test", memory_aux_max_retries=0, memory_aux_retry_backoff_s=0.25)
    restored = HarnessAgentConfig.from_dict(config.to_dict())
    assert restored.memory_aux_max_retries == 0
    assert restored.memory_aux_retry_backoff_s == 0.25
    for value in [-1, 11, True, 1.5]:
        with pytest.raises(ValueError, match="memory_aux_max_retries"):
            HarnessAgentConfig(name="test", memory_aux_max_retries=value)
    for value in [-1, 61, float("nan"), True]:
        with pytest.raises(ValueError, match="memory_aux_retry_backoff_s"):
            HarnessAgentConfig(name="test", memory_aux_retry_backoff_s=value)


@pytest.mark.parametrize("status", [408, 429, 503])
def test_transient_http_status_retries(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    calls = []

    def send(self: httpx.Client, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                status, request=request, json={"error": {"message": "temporary", "type": "server_error"}}
            )
        return _response(request)

    monkeypatch.setattr(httpx.Client, "send", send)
    factory = _factory()
    try:
        client = HarnessAgentLLMClient(factory, default_model="local/Qwen3", max_retries=1, retry_backoff_s=0)
        assert client.call_llm("probe") == "ok"
        assert len(calls) == 2
    finally:
        factory.close()


@pytest.mark.parametrize("provider_wide", [False, True])
def test_model_cache_invalidation_removes_memory_variant(provider_wide: bool) -> None:
    factory = _factory()
    chat = factory.get_chat_model("local/Qwen3")
    memory = factory.get_chat_model("local/Qwen3", max_retries=0)
    assert chat is not memory
    other = factory.get_chat_model("other/gpt-4.1", max_retries=0)
    if provider_wide:
        factory.clear_provider_cache("local")
    else:
        factory.pop_cached("local/Qwen3")
    assert factory.get_chat_model("local/Qwen3") is not chat
    assert factory.get_chat_model("local/Qwen3", max_retries=0) is not memory
    assert factory.get_chat_model("other/gpt-4.1", max_retries=0) is other
    factory.close()
