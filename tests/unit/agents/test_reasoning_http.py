"""Exercise reasoning overrides through real middleware, adapters, and SDK HTTP."""

import asyncio
import json
from contextlib import ExitStack

import httpx
import pytest
from langchain.agents.middleware import ModelRequest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from langchain_core.runnables.config import var_child_runnable_config
from langchain_openai import ChatOpenAI

from octop.infra.agents.middleware.reasoning import CONFIG_KEY, ReasoningRequestMiddleware
from octop.infra.agents.providers.reasoning import (
    reasoning_capability,
    reasoning_request_parameters,
)


@pytest.mark.parametrize("async_call", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("host", ["api.minimax.io", "api.minimaxi.com"])
@pytest.mark.parametrize(
    ("protocol", "model_id", "mode", "effort", "expected"),
    [
        ("openai", "MiniMax-M3.1-Flash", None, None, {"reasoning_effort": "max"}),
        ("openai", "MiniMax-M3.1-Flash", "saved_custom", None, {}),
        ("openai", "MiniMax-M3.1-Flash", "disabled", "xhigh", {"reasoning_effort": "xhigh"}),
        ("openai", "MiniMax-M3", None, None, {}),
        ("openai", "MiniMax-M3", "disabled", "max", {"thinking": {"type": "disabled"}}),
        ("openai", "MiniMax-M3", "enabled", "high", {"thinking": {"type": "adaptive"}}),
        ("openai", "MiniMax-M2.7", None, None, {}),
        (
            "anthropic",
            "MiniMax-M3.1-Flash",
            None,
            None,
            {"thinking": {"type": "adaptive"}, "output_config": {"effort": "max"}},
        ),
        (
            "anthropic",
            "MiniMax-M3.1-Flash",
            "disabled",
            "low",
            {"thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}},
        ),
        ("anthropic", "MiniMax-M3", None, None, {}),
        ("anthropic", "MiniMax-M3", "enabled", "max", {"thinking": {"type": "adaptive"}}),
        (
            "anthropic",
            "claude-opus-4-6",
            "enabled",
            "high",
            {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}},
        ),
    ],
)
def test_reasoning_middleware_serializes_http(
    monkeypatch, async_call, host, protocol, model_id, mode, effort, expected
) -> None:
    if model_id.startswith("claude"):
        host = "api.anthropic.com"
    base_url = f"https://{host}/{'v1' if protocol == 'openai' else 'anthropic'}"
    if model_id.startswith("claude"):
        base_url = f"https://{host}"
    metadata = {"id": model_id, "reasoning": True}
    if mode == "saved_custom":
        metadata["reasoning_config"] = {"adapter": "status_only", "toggle": False}
        mode = None
    if model_id.startswith("claude"):
        metadata["reasoning_config"] = {
            "adapter": "anthropic_adaptive",
            "efforts": ["high"],
        }
    capability = reasoning_capability(metadata, base_url=base_url)
    overrides = reasoning_request_parameters(capability, mode=mode, effort=effort)
    seen = []

    def transport(request):
        seen.append((str(request.url), json.loads(request.content)))
        if protocol == "openai":
            body = {
                "id": "fixture",
                "object": "chat.completion",
                "created": 0,
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            }
        else:
            body = {
                "id": "fixture",
                "type": "message",
                "role": "assistant",
                "model": model_id,
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        return httpx.Response(200, json=body)

    with ExitStack() as stack:
        client = stack.enter_context(httpx.Client(transport=httpx.MockTransport(transport)))
        async_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        if protocol == "openai":
            model = ChatOpenAI(
                model=model_id,
                api_key="fixture",
                base_url=base_url,
                max_retries=0,
                http_client=client,
                http_async_client=async_client,
                use_responses_api=False,
                extra_body={"fixture_custom_field": "preserved"},
            )
        else:
            monkeypatch.setattr(
                "langchain_anthropic.chat_models._get_default_httpx_client", lambda **_: client
            )
            monkeypatch.setattr(
                "langchain_anthropic.chat_models._get_default_async_httpx_client",
                lambda **_: async_client,
            )
            model = ChatAnthropic(
                model=model_id,
                api_key="fixture",
                base_url=base_url,
                max_tokens=128,
                max_retries=0,
            )
        original = model.model_dump()
        content = [{"type": "text", "text": "describe"}]
        if protocol == "openai":
            content.extend(
                [
                    {"type": "image_url", "image_url": {"url": "https://example.invalid/a.png"}},
                    {"type": "video_url", "video_url": {"url": "mm_file://fixture"}},
                ]
            )
        request = ModelRequest(model=model, messages=[HumanMessage(content=content)])
        token = var_child_runnable_config.set({"configurable": {CONFIG_KEY: overrides}})
        try:
            middleware = ReasoningRequestMiddleware()
            if async_call:

                async def invoke():
                    async def handler(configured):
                        return await configured.model.ainvoke(configured.messages)

                    try:
                        return await middleware.awrap_model_call(request, handler)
                    finally:
                        await async_client.aclose()

                response = asyncio.run(invoke())
            else:
                response = middleware.wrap_model_call(
                    request, lambda configured: configured.model.invoke(configured.messages)
                )
                asyncio.run(async_client.aclose())
        finally:
            var_child_runnable_config.reset(token)
        assert response.content == "ok"
        assert model.model_dump() == original

    assert len(seen) == 1
    url, payload = seen[0]
    suffix = "/chat/completions" if protocol == "openai" else "/v1/messages"
    assert url == base_url + suffix
    assert payload["model"] == model_id
    controls = {
        key: payload[key]
        for key in ("thinking", "reasoning_effort", "output_config")
        if key in payload and payload[key] is not None
    }
    assert controls == expected
    assert "service_tier" not in payload
    if protocol == "openai":
        assert payload["messages"][0]["content"] == content
        assert payload["fixture_custom_field"] == "preserved"
