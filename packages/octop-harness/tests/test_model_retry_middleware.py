"""Both retry paths must distinguish generated errors from model answers."""

from __future__ import annotations

from typing import Any

import pytest
from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage

from octop_harness.middleware.model_retry import ModelRetryMiddleware


def _retry() -> ModelRetryMiddleware:
    return ModelRetryMiddleware(
        max_retries=2,
        initial_delay=0,
        jitter=False,
        on_failure="error",
    )


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_sdk_http_errors_keep_original_retry_budget(status: int) -> None:
    import httpx
    from openai import APIStatusError

    error = APIStatusError(
        "opaque provider error",
        response=httpx.Response(status, request=httpx.Request("POST", "https://provider.example/v1/messages")),
        body={},
    )
    calls = 0

    def failed(_: Any) -> ModelResponse:
        nonlocal calls
        calls += 1
        raise error

    with pytest.raises(APIStatusError) as caught:
        _retry().wrap_model_call(None, failed)  # type: ignore[arg-type]
    assert caught.value is error
    assert calls == 3


@pytest.mark.parametrize("status", [408, 409, 429, 500, 503])
def test_transient_http_errors_still_retry_and_can_recover(status: int) -> None:
    import httpx

    error = httpx.HTTPStatusError(
        "temporary", request=httpx.Request("POST", "https://provider.example"), response=httpx.Response(status)
    )
    calls = 0
    success = ModelResponse(result=[AIMessage(content="Recovered")])

    def invoke(_: Any) -> ModelResponse:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise error
        return success

    assert _retry().wrap_model_call(None, invoke) is success  # type: ignore[arg-type]
    assert calls == 3


@pytest.mark.asyncio
async def test_async_sdk_auth_and_timeout_keep_original_retry_budget() -> None:
    import httpx
    from openai import AuthenticationError

    calls = 0
    error: Exception = AuthenticationError(
        "expired",
        response=httpx.Response(401, request=httpx.Request("POST", "https://provider.example/v1/messages")),
        body={},
    )

    async def invoke(_: Any) -> ModelResponse:
        nonlocal calls
        calls += 1
        raise error

    with pytest.raises(AuthenticationError):
        await _retry().awrap_model_call(None, invoke)  # type: ignore[arg-type]
    assert calls == 3
    calls = 0
    error = TimeoutError("request timed out")
    with pytest.raises(TimeoutError):
        await _retry().awrap_model_call(None, invoke)  # type: ignore[arg-type]
    assert calls == 3


@pytest.mark.asyncio
async def test_graph_records_failure_without_error_memory_and_can_resume(tmp_path: Any) -> None:
    import asyncio
    import threading

    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from langchain_core.exceptions import ModelAuthenticationError
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver
    from octop_memory import Memory, MemoryService

    from octop_harness.middleware.memory import MemoryMiddleware

    captured = threading.Event()

    class Service(MemoryService):
        def capture_turn(self, **kwargs: Any) -> dict[str, Any]:
            result = super().capture_turn(**kwargs)
            captured.set()
            return result

    class Model(FakeMessagesListChatModel):
        failing: bool = True
        attempts: int = 0

        def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
            return self

        def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> Any:
            self.attempts += 1
            if self.failing:
                raise ModelAuthenticationError("opaque credential rejection")
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

        async def _agenerate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> Any:
            return self._generate(messages, stop, run_manager, **kwargs)

    memory = Memory(namespace="retry_graph", backend_config={"db_path": str(tmp_path / "memory.sqlite")})
    service = Service(memory, config={"capture": {"min_message_chars": 0}})
    mw = MemoryMiddleware(service=service, jsonl_enabled=False)
    model = Model(responses=[AIMessage(content="Credentials fixed. The request succeeded.")])
    graph = create_deep_agent(
        model=model,
        middleware=[_retry(), mw],
        checkpointer=InMemorySaver(),
        backend=FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True),
    )
    config = {"configurable": {"thread_id": "failed-then-resumed"}}
    try:
        with pytest.raises(ModelAuthenticationError):
            await graph.ainvoke(
                {"messages": [HumanMessage(content="Remember my preference for Chinese replies.")]}, config
            )
        state = await graph.aget_state(config)
        assert any(task.error for task in state.tasks)
        assert not any(isinstance(message, AIMessage) for message in state.values["messages"])
        assert model.attempts == 1
        assert not memory.list_raw()
        assert not memory.list_atoms()
        model.failing = False
        await graph.ainvoke(None, config)
        assert await asyncio.to_thread(captured.wait, 2)
        assert memory.list_raw()
        assert all("opaque credential rejection" not in event.content for event in memory.list_raw())
        assert not any(task.error for task in (await graph.aget_state(config)).tasks)
    finally:
        mw.shutdown()
        memory.backend.close()


def fail(_: Any) -> ModelResponse:
    raise TimeoutError("request timed out")


def test_sync_exhausted_retry_is_marked() -> None:
    middleware = ModelRetryMiddleware(max_retries=0)
    response = middleware.wrap_model_call(None, fail)  # type: ignore[arg-type]
    assert isinstance(response, ModelResponse)
    assert response.result[0].response_metadata["octop_runtime_error"] is True
    assert "TimeoutError" in str(response.result[0].content)


@pytest.mark.asyncio
async def test_async_retry_marks_only_generated_failures() -> None:
    middleware = ModelRetryMiddleware(max_retries=0)

    async def afail(_: Any) -> ModelResponse:
        raise ConnectionError("connection lost")

    response = await middleware.awrap_model_call(None, afail)  # type: ignore[arg-type]
    assert isinstance(response, ModelResponse)
    assert response.result[0].response_metadata["octop_runtime_error"] is True

    success = ModelResponse(result=[AIMessage(content="401 排障经验: 刷新凭据后验证成功。")])

    async def succeed(_: Any) -> ModelResponse:
        return success

    assert await middleware.awrap_model_call(None, succeed) is success  # type: ignore[arg-type]
    assert "octop_runtime_error" not in success.result[0].response_metadata
