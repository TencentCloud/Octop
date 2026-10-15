"""Exercise cumulative SSE usage through the real OpenAI/LangGraph adapters."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler, CallbackManager
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from octop_harness.middleware.context_usage import ContextUsageMiddleware

from octop.infra.agents.middleware.stream_usage import StreamUsageMiddleware
from octop.infra.agents.threads.context_breakdown import usage_dict_from_message


def _sse(usage_samples: list[tuple[int, int]]) -> bytes:
    rows = []
    for index, (prompt, output) in enumerate(usage_samples):
        rows.append(
            "data: "
            + json.dumps(
                {
                    "id": "call-1",
                    "object": "chat.completion.chunk",
                    "model": "Qwen3.8-flash",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": "你好" if index == 0 else ""},
                            "finish_reason": "stop" if index == len(usage_samples) - 1 else None,
                        }
                    ],
                    "usage": {
                        "prompt_tokens": prompt,
                        "completion_tokens": output,
                        "total_tokens": prompt + output,
                        "prompt_tokens_details": {"cached_tokens": prompt // 2},
                    },
                }
            )
            + "\n\n"
        )
    return ("".join(rows) + "data: [DONE]\n\n").encode()


@pytest.fixture
def model() -> Iterator[ChatOpenAI]:
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        text = body["messages"][-1]["content"]
        if text == "terminal":
            samples = [(16_244, 112)]
        elif text == "delta":
            samples = [(16_244, 0), (0, 60), (0, 52)]
        else:
            samples = [(16_244, n * 2) for n in range(1, 57)]
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_sse(samples)
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        async_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        chat_model = ChatOpenAI(
            model="Qwen3.8-flash",
            base_url="http://test.invalid/v1",
            api_key="test",
            http_client=client,
            http_async_client=async_client,
            streaming=True,
            stream_usage=False,
            profile={"max_input_tokens": 262_144},
        )
        try:
            yield chat_model
        finally:
            asyncio.run(async_client.aclose())


def _graph(model: ChatOpenAI) -> Any:
    return create_agent(
        model,
        tools=[],
        middleware=[StreamUsageMiddleware(), ContextUsageMiddleware(max_tokens=262_144)],
    )


def _assert_usage(message: AIMessage) -> None:
    assert message.usage_metadata is not None
    assert message.usage_metadata["input_tokens"] == 16_244
    assert message.usage_metadata["output_tokens"] == 112
    assert message.usage_metadata["input_token_details"]["cache_read"] == 8_122
    snapshot = message.additional_kwargs["context_usage"]
    assert snapshot["used_tokens"] == 16_244
    assert snapshot["max_tokens"] == 262_144
    assert round(snapshot["used_tokens"] / snapshot["max_tokens"] * 100) == 6
    history_usage = usage_dict_from_message(message)
    assert history_usage is not None
    assert history_usage["input_tokens"] == 16_244
    assert history_usage["output_tokens"] == 112


@pytest.mark.parametrize("text", ["哈喽", "terminal", "delta"])
def test_sync_context_and_history_use_actual_prompt(model: ChatOpenAI, text: str) -> None:
    result = _graph(model).invoke({"messages": [{"role": "user", "content": text}]})
    _assert_usage(result["messages"][-1])
    assert model.callbacks is None


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_manager", [False, True])
async def test_async_stream_keeps_live_usage_and_concurrent_calls_isolated(
    model: ChatOpenAI, callback_manager: bool
) -> None:
    seen: list[int] = []

    class Observer(BaseCallbackHandler):
        run_inline = True

        def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
            usage = kwargs["chunk"].message.usage_metadata
            if usage:
                seen.append(usage["input_tokens"])

    observer = Observer()
    existing = CallbackManager([observer]) if callback_manager else [observer]
    model.callbacks = existing
    graph = _graph(model)

    async def run(text: str) -> None:
        result = await graph.ainvoke({"messages": [{"role": "user", "content": text}]})
        _assert_usage(result["messages"][-1])

    await asyncio.gather(run("哈喽"), run("terminal"))
    assert seen == [16_244] * 57
    assert model.callbacks is existing
    assert (existing.handlers if callback_manager else existing) == [observer]
