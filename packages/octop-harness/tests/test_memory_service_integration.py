"""Tests for the MemoryService-backed integration.

These exercise the ``MemoryService`` plumbing:

* ``HarnessAgentLLMClient`` adapts the agent's :class:`ChatModelFactory`
  to the :class:`octop_memory.ports.llm.LLMClient` protocol and degrades to
  ``LLMClientError`` on failure.
* ``MemoryMiddleware`` recalls (read path) and captures (write path)
  through ``MemoryService``.
* ``build_memory_tools`` produces the ``memory_search`` /
  ``memory_get`` pair routed through ``MemoryService``.
* ``HarnessAgentConfig.memory_namespace`` defaults to ``config.name``.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage
from octop_memory import Memory, MemoryService
from octop_memory.ports.llm import LLMClient, LLMClientError

from octop_harness.builtin.tools.memory_tools import build_memory_tools
from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.memory.llm_client import HarnessAgentLLMClient
from octop_harness.memory.runtime import MemoryRuntime
from octop_harness.middleware.memory import MemoryMiddleware

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory(tmp_path: Path) -> Iterator[Memory]:
    mem = Memory(namespace="t", backend_config={"db_path": str(tmp_path / "m.sqlite")})
    yield mem


@pytest.fixture
def service(memory: Memory) -> MemoryService:
    return MemoryService(memory, host="octop-harness-tests")


# ---------------------------------------------------------------------------
# HarnessAgentLLMClient
# ---------------------------------------------------------------------------


class _FakeMsg:
    def __init__(self, content: object) -> None:
        self.content = content


class _FakeModel:
    def __init__(self, content: str = "ok") -> None:
        self._content = content
        self.bind_calls: list[dict[str, Any]] = []
        self.invoke_messages: list[Any] | None = None

    def bind(self, **kwargs: Any) -> _FakeModel:
        self.bind_calls.append(kwargs)
        return self

    def invoke(self, messages: list[Any]) -> _FakeMsg:
        self.invoke_messages = messages
        return _FakeMsg(self._content)


class _BadModel(_FakeModel):
    def invoke(self, messages: list[Any]) -> _FakeMsg:
        raise RuntimeError("boom")


class _FakeOpenAIModel(_FakeModel):
    pass


_FakeOpenAIModel.__module__ = "langchain_openai.chat_models.base"


class _FakeAnthropicModel(_FakeModel):
    pass


_FakeAnthropicModel.__module__ = "langchain_anthropic.chat_models"


class _Factory:
    def __init__(self, model: _FakeModel) -> None:
        self.model = model
        self.last_ref: str | None = None
        self.refs: list[str] = []

    def get(self, ref: str) -> _FakeModel:
        self.last_ref = ref
        self.refs.append(ref)
        return self.model

    def get_chat_model(self, ref: str, *, max_retries: int | None = None) -> _FakeModel:
        return self.get(ref)


class _MapFactory:
    def __init__(self, models: dict[str, _FakeModel | BaseException]) -> None:
        self.models = models
        self.refs: list[str] = []

    def get(self, ref: str) -> _FakeModel:
        self.refs.append(ref)
        model = self.models[ref]
        if isinstance(model, BaseException):
            raise model
        return model

    def get_chat_model(self, ref: str, *, max_retries: int | None = None) -> _FakeModel:
        return self.get(ref)


class TestHarnessAgentLLMClient:
    def test_implements_protocol(self) -> None:
        client = HarnessAgentLLMClient(_Factory(_FakeModel()), default_model="p/m")
        assert isinstance(client, LLMClient)

    def test_complete_returns_text(self) -> None:
        factory = _Factory(_FakeModel("hello"))
        client = HarnessAgentLLMClient(factory, default_model="p/m")
        out = client.call_llm("hi", system="be brief")
        assert out == "hello"
        assert factory.last_ref == "p/m"

    def test_light_and_heavy_share_one_aux(self) -> None:
        factory = _Factory(_FakeModel("ok"))
        client = HarnessAgentLLMClient(
            factory,
            light_model="p/aux",
            heavy_model="p/other",
            default_model="p/m",
        )
        client.call_llm("x", tier="light")
        assert factory.last_ref == "p/aux"
        client.call_llm("x", tier="heavy")
        assert factory.last_ref == "p/aux"

    def test_no_aux_uses_current_chat_model(self) -> None:
        factory = _Factory(_FakeModel("ok"))
        client = HarnessAgentLLMClient(factory, default_model="p/default")
        client.set_current_model("dashscope/qwen")
        client.call_llm("x")
        assert factory.last_ref == "dashscope/qwen"

    def test_no_aux_no_current_uses_default(self) -> None:
        factory = _Factory(_FakeModel("ok"))
        client = HarnessAgentLLMClient(factory, default_model="p/default")
        client.call_llm("x")
        assert factory.last_ref == "p/default"

    def test_aux_overrides_current_chat_model(self) -> None:
        factory = _Factory(_FakeModel("ok"))
        client = HarnessAgentLLMClient(factory, aux_model="p/aux", default_model="p/default")
        client.set_current_model("dashscope/qwen")
        client.call_llm("x")
        assert factory.last_ref == "p/aux"

    def test_legacy_heavy_alias_is_aux_when_light_unset(self) -> None:
        factory = _Factory(_FakeModel("ok"))
        client = HarnessAgentLLMClient(factory, heavy_model="p/heavy", default_model="p/default")
        client.call_llm("x", tier="light")
        assert factory.last_ref == "p/heavy"

    def test_failure_wraps_in_llm_client_error(self) -> None:
        client = HarnessAgentLLMClient(_Factory(_BadModel()), default_model="p/m")
        with pytest.raises(LLMClientError):
            client.call_llm("anything")

    def test_provider_400_is_wrapped_not_raised_raw(self) -> None:
        class _SubscriptionExpiredError(Exception):
            """Mirrors openai.BadRequestError — not a RuntimeError/OSError."""

        class _ExpiredModel(_FakeModel):
            def invoke(self, messages: list[Any]) -> _FakeMsg:
                raise _SubscriptionExpiredError("InvalidSubscription")

        client = HarnessAgentLLMClient(_Factory(_ExpiredModel()), default_model="p/m")
        with pytest.raises(LLMClientError, match="InvalidSubscription"):
            client.call_llm("anything")

    def test_failed_aux_falls_back_to_current_model(self) -> None:
        class _SubscriptionExpiredError(Exception):
            pass

        class _ExpiredModel(_FakeModel):
            def invoke(self, messages: list[Any]) -> _FakeMsg:
                raise _SubscriptionExpiredError("InvalidSubscription")

        factory = _MapFactory(
            {
                "ark/expired": _ExpiredModel(),
                "dashscope/qwen": _FakeModel("extracted"),
            }
        )
        client = HarnessAgentLLMClient(
            factory,
            light_model="ark/expired",
            default_model="ark/expired",
        )
        client.set_current_model("dashscope/qwen")
        assert client.call_llm("x") == "extracted"
        assert factory.refs == ["ark/expired", "dashscope/qwen"]

    def test_failed_aux_falls_back_to_default_when_no_current_model(self) -> None:
        class _ExpiredModel(_FakeModel):
            def invoke(self, messages: list[Any]) -> _FakeMsg:
                raise RuntimeError("400")

        factory = _MapFactory(
            {
                "ark/expired": _ExpiredModel(),
                "dashscope/qwen": _FakeModel("ok"),
            }
        )
        client = HarnessAgentLLMClient(
            factory,
            light_model="ark/expired",
            default_model="dashscope/qwen",
        )
        assert client.call_llm("x") == "ok"
        assert factory.refs == ["ark/expired", "dashscope/qwen"]

    def test_successful_aux_does_not_touch_fallback(self) -> None:
        factory = _MapFactory(
            {
                "ark/ok": _FakeModel("primary"),
                "dashscope/qwen": _FakeModel("fallback"),
            }
        )
        client = HarnessAgentLLMClient(
            factory,
            light_model="ark/ok",
            default_model="dashscope/qwen",
        )
        client.set_current_model("dashscope/qwen")
        assert client.call_llm("x") == "primary"
        assert factory.refs == ["ark/ok"]

    def test_fallback_also_failing_still_wraps(self) -> None:
        class _ExpiredModel(_FakeModel):
            def invoke(self, messages: list[Any]) -> _FakeMsg:
                raise RuntimeError("still-dead")

        factory = _MapFactory(
            {
                "ark/expired": _ExpiredModel(),
                "dashscope/qwen": _ExpiredModel(),
            }
        )
        client = HarnessAgentLLMClient(
            factory,
            light_model="ark/expired",
            default_model="dashscope/qwen",
        )
        with pytest.raises(LLMClientError, match="still-dead"):
            client.call_llm("anything")
        assert factory.refs == ["ark/expired", "dashscope/qwen"]

    def test_json_response_format_hint_is_openai_only(self) -> None:
        openai_model = _FakeOpenAIModel()
        openai_client = HarnessAgentLLMClient(_Factory(openai_model), default_model="p/m")
        openai_client.call_llm("x", temperature=0.0, response_format="json")
        assert openai_model.bind_calls[-1] == {
            "temperature": 0.0,
            "timeout": HarnessAgentLLMClient.DEFAULT_LIGHT_TIMEOUT_S,
            "response_format": {"type": "json_object"},
        }

        anthropic_model = _FakeAnthropicModel()
        anthropic_client = HarnessAgentLLMClient(_Factory(anthropic_model), default_model="p/m")
        anthropic_client.call_llm("x", temperature=0.0, response_format="json")
        assert anthropic_model.bind_calls[-1] == {
            "temperature": 0.0,
            "timeout": HarnessAgentLLMClient.DEFAULT_LIGHT_TIMEOUT_S,
        }

    def test_requires_at_least_one_ref(self) -> None:
        with pytest.raises(ValueError):
            HarnessAgentLLMClient(_Factory(_FakeModel()))

    def test_strips_inline_think_tags_from_string_content(self) -> None:
        factory = _Factory(_FakeModel('<think>let me reason...</think>{"candidates": []}'))
        client = HarnessAgentLLMClient(factory, default_model="p/m")
        out = client.call_llm("x")
        assert out == '{"candidates": []}'

    def test_auto_disables_thinking_only_for_reasoning_model_ids(self) -> None:
        qwen = _FakeOpenAIModel()
        client = HarnessAgentLLMClient(_Factory(qwen), default_model="local/Qwen3.8-Flash-Next")
        client.call_llm("x", tier="light", max_tokens=2048)
        assert qwen.bind_calls[-1]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
        assert qwen.bind_calls[-1]["max_tokens"] == 2048
        assert qwen.bind_calls[-1]["timeout"] == HarnessAgentLLMClient.DEFAULT_LIGHT_TIMEOUT_S

        plain = _FakeOpenAIModel()
        HarnessAgentLLMClient(_Factory(plain), default_model="openai/gpt-4.1").call_llm("x")
        assert "extra_body" not in plain.bind_calls[-1]

    def test_thinking_off_binds_for_supported_model(self) -> None:
        model = _FakeOpenAIModel()
        client = HarnessAgentLLMClient(
            _Factory(model),
            default_model="local/Qwen3",
            light_timeout_s=45,
            heavy_timeout_s=90,
            thinking="off",
        )
        client.call_llm("x", tier="heavy")
        assert model.bind_calls[-1]["timeout"] == 90
        assert model.bind_calls[-1]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}

    def test_thinking_on_and_anthropic_skip_extra_body(self) -> None:
        openai_model = _FakeOpenAIModel()
        HarnessAgentLLMClient(
            _Factory(openai_model),
            default_model="local/Qwen3-8B",
            thinking="on",
        ).call_llm("x")
        assert "extra_body" not in openai_model.bind_calls[-1]

        anthropic_model = _FakeAnthropicModel()
        HarnessAgentLLMClient(
            _Factory(anthropic_model),
            default_model="local/Qwen3-8B",
            thinking="off",
        ).call_llm("x")
        assert "extra_body" not in anthropic_model.bind_calls[-1]

    def test_caller_max_tokens_is_forwarded(self) -> None:
        model = _FakeOpenAIModel()
        HarnessAgentLLMClient(_Factory(model), default_model="p/m").call_llm("x", max_tokens=512)
        assert model.bind_calls[-1]["max_tokens"] == 512

    def test_skips_thinking_blocks_in_list_content(self) -> None:
        blocks = [
            {"type": "thinking", "text": "internal reasoning"},
            {"type": "text", "text": '{"candidates": []}'},
        ]
        factory = _Factory(_FakeModel(blocks))
        client = HarnessAgentLLMClient(factory, default_model="p/m")
        out = client.call_llm("x")
        assert out == '{"candidates": []}'

    def test_timeout_overrides_and_default_budget_are_bound(self) -> None:
        openai_model = _FakeOpenAIModel()
        client = HarnessAgentLLMClient(
            _Factory(openai_model),
            default_model="p/m",
            light_timeout_s=42.0,
            heavy_timeout_s=90.0,
            default_max_tokens=256,
        )
        client.call_llm("x")
        assert openai_model.bind_calls[-1]["timeout"] == 42.0
        assert openai_model.bind_calls[-1]["max_tokens"] == 256

        client.call_llm("x", tier="heavy")
        assert openai_model.bind_calls[-1]["timeout"] == 90.0

    def test_caller_budget_wins_over_default_budget(self) -> None:
        openai_model = _FakeOpenAIModel()
        client = HarnessAgentLLMClient(_Factory(openai_model), default_model="p/m", default_max_tokens=256)
        client.call_llm("x", max_tokens=99)
        assert openai_model.bind_calls[-1]["max_tokens"] == 99

    def test_no_default_budget_leaves_max_tokens_unbound(self) -> None:
        openai_model = _FakeOpenAIModel()
        client = HarnessAgentLLMClient(_Factory(openai_model), default_model="p/m")
        client.call_llm("x")
        assert "max_tokens" not in openai_model.bind_calls[-1]

    def test_extra_body_is_openai_only(self) -> None:
        openai_model = _FakeOpenAIModel()
        openai_client = HarnessAgentLLMClient(
            _Factory(openai_model),
            default_model="p/m",
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        openai_client.call_llm("x")
        assert openai_model.bind_calls[-1]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}

        anthropic_model = _FakeAnthropicModel()
        anthropic_client = HarnessAgentLLMClient(
            _Factory(anthropic_model),
            default_model="p/m",
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        anthropic_client.call_llm("x")
        assert "extra_body" not in anthropic_model.bind_calls[-1]

    def test_explicit_extra_body_overrides_thinking_switch(self) -> None:
        model = _FakeOpenAIModel()
        client = HarnessAgentLLMClient(
            _Factory(model),
            default_model="local/Qwen3-8B",
            extra_body={
                "reasoning_effort": "low",
                "chat_template_kwargs": {"enable_thinking": True},
            },
        )
        client.call_llm("x")
        assert model.bind_calls[-1]["extra_body"] == {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_effort": "low",
        }


def test_memory_runtime_writes_budget_into_extraction_config(tmp_path: Path) -> None:
    """The extractor ignores a client-side max_tokens fallback, so the host budget goes to the runtime."""
    cfg = HarnessAgentConfig(
        name="agent",
        workspace_dir=tmp_path,
        providers=[
            ProviderConfig(
                id="local",
                base_url="http://127.0.0.1:8000/v1",
                api_key="k",
                models=[ModelConfig(id="Qwen3")],
            )
        ],
        default_model="local/Qwen3",
        memory_backend={"type": "sqlite", "db_path": str(tmp_path / "mem.sqlite")},
        memory_extract_max_tokens=1024,
        memory_aux_light_timeout_s=45,
        memory_aux_heavy_timeout_s=90,
        memory_aux_thinking="off",
        memory_aux_max_tokens=256,
        memory_aux_extra_body={"reasoning_effort": "low"},
        session_log_enabled=False,
        checkpointer=False,
    )
    runtime = MemoryRuntime(config=cfg, workspace_path=tmp_path, model_factory=MagicMock())
    try:
        extraction = runtime.service._runtime._extraction_cfg()
        assert extraction["max_tokens"] == 1024
        assert runtime._llm_client is not None
        assert runtime._llm_client._light_timeout_s == 45
        assert runtime._llm_client._heavy_timeout_s == 90
        assert runtime._llm_client._thinking == "off"
        assert runtime._llm_client._default_max_tokens == 256
        assert runtime._llm_client._extra_body == {"reasoning_effort": "low"}
    finally:
        runtime.close()


# ---------------------------------------------------------------------------
# MemoryMiddleware: service-backed paths
# ---------------------------------------------------------------------------


def _make_runtime(thread_id: str = "t1") -> MagicMock:
    runtime = MagicMock()
    runtime.config = {"configurable": {"thread_id": thread_id, "user": "u", "source": "test"}}
    return runtime


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _StubService:
    """Spy wrapper around MemoryService that records calls but stays in-process."""

    def __init__(self, real: MemoryService) -> None:
        self._real = real
        self.recall_calls: list[dict[str, Any]] = []
        self.capture_calls: list[dict[str, Any]] = []
        self.extract_calls: list[dict[str, Any]] = []
        self._capture_event = threading.Event()
        self._extract_event = threading.Event()
        self.memory = real.memory

    def recall(
        self,
        query: str,
        *,
        thread_id: str | None = None,
        session_id: str | None = None,
        limit: int = 5,
    ):
        self.recall_calls.append({"query": query, "thread_id": thread_id, "session_id": session_id, "limit": limit})
        return self._real.recall(query, thread_id=thread_id, session_id=session_id, limit=limit)

    def search(self, query: str, *, max_results: int = 5, corpus: str = "all", thread_id: str | None = None):
        return self._real.search(query, max_results=max_results, corpus=corpus, thread_id=thread_id)

    def get(self, path: str, *, start: int | None = None, lines: int | None = None):
        return self._real.get(path, start=start, lines=lines)

    def capture_turn(self, **kwargs: Any) -> dict[str, Any]:
        self.capture_calls.append(kwargs)
        result = self._real.capture_turn(**kwargs)
        self._capture_event.set()
        return result

    def extract(self, session_id: str, **kwargs: Any) -> dict[str, Any]:
        self.extract_calls.append({"session_id": session_id, **kwargs})
        self._extract_event.set()
        return {"failure_reason": "no llm in test"}

    def wait_for_capture(self, timeout: float = 2.0) -> bool:
        return self._capture_event.wait(timeout)

    def wait_for_extract(self, timeout: float = 2.0) -> bool:
        return self._extract_event.wait(timeout)


class TestMemoryMiddlewareWithService:
    def test_capture_routes_through_service(
        self,
        memory: Memory,
        service: MemoryService,
        tmp_path: Path,
    ) -> None:
        spy = _StubService(service)
        mw = MemoryMiddleware(
            service=spy,  # type: ignore[arg-type]
            jsonl_enabled=False,
        )
        runtime = _make_runtime()

        u = HumanMessage(content="What's the plan?")
        a = AIMessage(content="Ship by Friday.")
        mw.before_model({"messages": [u]}, runtime)
        mw.after_model({"messages": [u, a]}, runtime)

        assert spy.wait_for_capture(timeout=2.0)
        assert len(spy.capture_calls) == 1
        call = spy.capture_calls[0]
        assert call["user"] == "What's the plan?"
        assert call["assistant"] == "Ship by Friday."
        assert call["thread_id"] == "t1"

    def test_recall_injection_preserves_system_and_clean_user_content(
        self,
        memory: Memory,
        service: MemoryService,
    ) -> None:
        # Seed an atom-ish memory the service can recall.
        memory.store("Project deadline is Friday", topic="deadline")

        spy = _StubService(service)
        mw = MemoryMiddleware(service=spy, jsonl_enabled=False)  # type: ignore[arg-type]

        # A real ModelRequest: ``system_prompt`` is a read-only property on
        # langchain >= 1.x, so this test fails if injection tries to mutate
        # the request instead of going through ``override()``.
        user = HumanMessage(content="When is the deadline?", id="deadline-question")
        update = mw.before_model({"messages": [user]}, _make_runtime())
        assert update is not None
        request = ModelRequest(
            model=MagicMock(),
            messages=update["messages"],
            system_prompt="You are helpful.",
        )

        captured: list[Any] = []

        def handler(req: Any) -> Any:
            captured.append(req)
            return MagicMock()

        mw.wrap_model_call(request, handler)

        assert len(spy.recall_calls) == 1
        assert spy.recall_calls[0]["query"] == "When is the deadline?"
        # The handler receives the augmented request (we don't assert the
        # exact rendered block — that's octop-memory's job to format).
        assert len(captured) == 1
        assert captured[0].system_prompt == "You are helpful."
        assert "Project deadline is Friday" in captured[0].messages[0].content
        assert request.messages[0].content == user.content

    def test_recall_disabled_skips_call(
        self,
        memory: Memory,
        service: MemoryService,
    ) -> None:
        spy = _StubService(service)
        mw = MemoryMiddleware(
            service=spy,  # type: ignore[arg-type]
            recall_inject_enabled=False,
            jsonl_enabled=False,
        )
        request = MagicMock()
        request.messages = [HumanMessage(content="anything")]
        request.system_prompt = "sys"

        mw.wrap_model_call(request, lambda r: MagicMock())

        assert spy.recall_calls == []

    def test_capture_disabled_skips_call(
        self,
        memory: Memory,
        service: MemoryService,
    ) -> None:
        spy = _StubService(service)
        mw = MemoryMiddleware(
            service=spy,  # type: ignore[arg-type]
            capture_enabled=False,
            jsonl_enabled=False,
        )
        runtime = _make_runtime()

        u = HumanMessage(content="hi")
        a = AIMessage(content="hello")
        mw.before_model({"messages": [u]}, runtime)
        mw.after_model({"messages": [u, a]}, runtime)

        # Give any rogue background task a chance to fire.
        time.sleep(0.05)
        assert spy.capture_calls == []

    def test_end_session_calls_extract(
        self,
        memory: Memory,
        service: MemoryService,
    ) -> None:
        spy = _StubService(service)
        mw = MemoryMiddleware(service=spy, jsonl_enabled=False)  # type: ignore[arg-type]

        # Synchronous mode for deterministic assertion.
        mw.end_session("session-1", background=False)

        assert len(spy.extract_calls) == 1
        assert spy.extract_calls[0]["session_id"] == "session-1"


# ---------------------------------------------------------------------------
# build_memory_tools
# ---------------------------------------------------------------------------


class TestMemoryTools:
    def test_returns_recall_tools(self, service: MemoryService) -> None:
        tools = build_memory_tools(service)
        assert {t.name for t in tools} == {"memory_search", "memory_get", "memory_save"}

    def test_explicit_save_creates_recallable_atom_without_editing_strong_memory(
        self,
        service: MemoryService,
        memory: Memory,
        tmp_path: Path,
    ) -> None:
        strong = tmp_path / "MEMORY.md"
        strong.write_text("User-maintained instructions", encoding="utf-8")
        save = next(t for t in build_memory_tools(service) if t.name == "memory_save")
        result = save.invoke({"content": "Project Aurora uses PostgreSQL", "topic": "Aurora"})
        assert "saved" in result.lower()
        assert memory.search_atoms("PostgreSQL")
        assert strong.read_text(encoding="utf-8") == "User-maintained instructions"

    def test_memory_search_empty(self, service: MemoryService) -> None:
        tools = build_memory_tools(service)
        search = next(t for t in tools if t.name == "memory_search")
        out = search.invoke({"query": "nothing-anywhere"})
        assert "No matching memory entries" in out

    def test_memory_search_finds_seeded_atom(
        self,
        service: MemoryService,
        memory: Memory,
    ) -> None:
        memory.store("Likes dark mode", topic="ui")
        tools = build_memory_tools(service)
        search = next(t for t in tools if t.name == "memory_search")
        out = search.invoke({"query": "dark mode", "max_results": 5})
        # We don't assert the formatting verbatim — just that recall fired
        # and we didn't get the empty-reason path.
        assert "No matching memory entries" not in out


# ---------------------------------------------------------------------------
# Namespace default = config.name
# ---------------------------------------------------------------------------


class TestNamespaceDefault:
    def test_memory_namespace_falls_back_to_name(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig

        cfg = HarnessAgentConfig(
            name="agent-alpha",
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": True},
            providers=[
                ProviderConfig(id="p", base_url="https://x", api_key="k", models=[ModelConfig(id="m")]),
            ],
            memory_enabled=True,
            memory_backend={"type": "sqlite", "db_path": str(tmp_path / "mem.sqlite")},
        )
        # No explicit memory_namespace → expected to default to ``name``.
        assert cfg.memory_namespace is None
        from octop_harness.agent import HarnessAgent

        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
            patch("deepagents.create_deep_agent", return_value=MagicMock()),
        ):
            agent = HarnessAgent(cfg)
        assert agent.memory is not None
        assert agent.memory.namespace == "agent-alpha"
        agent.close()
