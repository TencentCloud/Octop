"""Tests for ``octop_harness.llm.factory``."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from octop_harness.config import ModelConfig, ProviderConfig
from octop_harness.llm.factory import (
    ChatModelFactory,
    _get_reasoning_aware_chat_openai,
    _is_responses_api_unsupported_error,
    build_chat_model,
)


class TestBuildChatModel:
    def test_openai_protocol_invokes_chat_openai(self) -> None:
        provider = ProviderConfig(
            id="example",
            base_url="https://api.example.com/v1",
            api_key="sk-x",
            protocol="openai",
            headers={"X-Trace": "1"},
        )
        model = ModelConfig(id="gpt-X")
        # The subclass is built lazily off the live ``ChatOpenAI`` and cached
        # on first use, so we patch the subclass directly to assert the kwargs
        # that reach the constructor.
        from langchain_openai import ChatOpenAI

        cls = _get_reasoning_aware_chat_openai(ChatOpenAI)
        with patch.object(cls, "__init__", return_value=None) as mock_init:
            build_chat_model(provider, model)
        mock_init.assert_called_once()
        kwargs = mock_init.call_args.kwargs
        assert kwargs["model"] == "gpt-X"
        assert kwargs["base_url"] == "https://api.example.com/v1"
        assert kwargs["api_key"] == "sk-x"
        assert kwargs["default_headers"] == {"X-Trace": "1"}
        # Custom base_url disables langchain-openai's stream_usage default,
        # so the factory must pass it explicitly or streamed responses carry
        # no usage_metadata.
        assert kwargs["stream_usage"] is True
        assert kwargs["use_responses_api"] is False
        assert "output_version" not in kwargs

    def test_openai_protocol_stream_usage_opt_out(self) -> None:
        provider = ProviderConfig(
            id="example",
            base_url="https://api.example.com/v1",
            api_key="sk-x",
            protocol="openai",
            stream_usage=False,
        )
        model = ModelConfig(id="gpt-X")
        from langchain_openai import ChatOpenAI

        cls = _get_reasoning_aware_chat_openai(ChatOpenAI)
        with patch.object(cls, "__init__", return_value=None) as mock_init:
            build_chat_model(provider, model)
        assert mock_init.call_args.kwargs["stream_usage"] is False

    def test_openai_native_tool_search_enables_responses_api(self) -> None:
        provider = ProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-x",
            protocol="openai",
        )
        model = ModelConfig(id="gpt-tool-search", api_mode="responses", native_tool_search=True)
        from langchain_openai import ChatOpenAI

        cls = _get_reasoning_aware_chat_openai(ChatOpenAI)
        with patch.object(cls, "__init__", return_value=None) as mock_init:
            instance = build_chat_model(provider, model)

        kwargs = mock_init.call_args.kwargs
        assert kwargs["use_responses_api"] is True
        assert kwargs["output_version"] == "responses/v1"
        assert instance._harness_native_tool_search is True
        assert instance._harness_tool_search_provider == "openai"

    @pytest.mark.parametrize(
        ("api_mode", "expected"),
        [("responses", True), ("chat_completions", False)],
    )
    def test_openai_explicit_api_mode_overrides_endpoint(self, api_mode: str, expected: bool) -> None:
        provider = ProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-x",
            protocol="openai",
        )
        model = ModelConfig(id="gpt-X", api_mode=api_mode)  # type: ignore[arg-type]
        from langchain_openai import ChatOpenAI

        cls = _get_reasoning_aware_chat_openai(ChatOpenAI)
        with patch.object(cls, "__init__", return_value=None) as mock_init:
            build_chat_model(provider, model)

        assert mock_init.call_args.kwargs["use_responses_api"] is expected

    def test_openai_native_tool_search_rejects_chat_completions(self) -> None:
        provider = ProviderConfig(id="openai", base_url="https://api.example.com/v1", api_key="sk-x")
        model = ModelConfig(id="gpt-X", api_mode="chat_completions", native_tool_search=True)

        with pytest.raises(ValueError, match="native_tool_search requires api_mode='responses'"):
            build_chat_model(provider, model)

    def test_openai_responses_fallback_builds_chat_completions_model(self) -> None:
        provider = ProviderConfig(id="openai", base_url="https://api.example.com/v1", api_key="sk-x")
        model = ModelConfig(
            id="gpt-X",
            api_mode="responses",
            api_fallback="chat_completions",
        )
        from langchain_openai import ChatOpenAI

        cls = _get_reasoning_aware_chat_openai(ChatOpenAI)
        with patch.object(cls, "__init__", return_value=None) as mock_init:
            instance = build_chat_model(provider, model)

        assert mock_init.call_count == 2
        primary_kwargs = mock_init.call_args_list[0].kwargs
        fallback_kwargs = mock_init.call_args_list[1].kwargs
        assert primary_kwargs["use_responses_api"] is True
        assert primary_kwargs["output_version"] == "responses/v1"
        assert fallback_kwargs["use_responses_api"] is False
        assert "output_version" not in fallback_kwargs
        assert instance._harness_api_fallback_model is not None

    def test_openai_profile_includes_distinct_context_limits(self) -> None:
        provider = ProviderConfig(
            id="example",
            base_url="https://api.example.com/v1",
            api_key="sk-x",
            protocol="openai",
        )
        model = ModelConfig(
            id="deepseek-v4-pro",
            max_input_tokens=1_000_000,
            context_window=1_000_000,
            max_output_tokens=384_000,
        )
        instance = build_chat_model(provider, model)
        assert instance.profile is not None
        assert instance.profile["max_input_tokens"] == 1_000_000
        assert instance.profile["context_window"] == 1_000_000
        assert instance.profile["max_output_tokens"] == 384_000

    def test_openai_returns_reasoning_aware_subclass(self) -> None:
        """``protocol="openai"`` must use the reasoning_content-aware subclass."""
        from langchain_openai import ChatOpenAI

        provider = ProviderConfig(
            id="example",
            base_url="https://api.example.com/v1",
            api_key="sk-x",
            protocol="openai",
        )
        model = ModelConfig(id="gpt-X")
        instance = build_chat_model(provider, model)
        assert isinstance(instance, ChatOpenAI)
        assert type(instance).__name__ == "_ReasoningAwareChatOpenAI"

    def test_anthropic_protocol_invokes_chat_anthropic(self) -> None:
        provider = ProviderConfig(
            id="anthropic",
            base_url="https://api.anthropic.com",
            api_key="sk-y",
            protocol="anthropic",
        )
        model = ModelConfig(id="claude-x")
        with patch("langchain_anthropic.ChatAnthropic") as mock_cls:
            build_chat_model(provider, model)
        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["model"] == "claude-x"
        assert kwargs["api_key"] == "sk-y"

    def test_anthropic_native_tool_search_stamps_capability(self) -> None:
        provider = ProviderConfig(
            id="anthropic",
            base_url="https://api.anthropic.com",
            api_key="sk-y",
            protocol="anthropic",
        )
        model = ModelConfig(id="claude-tool-search", native_tool_search=True)
        with patch("langchain_anthropic.ChatAnthropic"):
            instance = build_chat_model(provider, model)

        assert instance._harness_native_tool_search is True
        assert instance._harness_tool_search_provider == "anthropic"

    def test_bedrock_protocol_reports_clear_import_error_when_missing(self) -> None:
        """When ``langchain_aws`` is not importable, surface a clear instruction."""
        provider = ProviderConfig(
            id="bedrock",
            base_url="https://bedrock-runtime.us-east-1.amazonaws.com",
            api_key="aws-x",
            protocol="bedrock",
        )
        model = ModelConfig(id="anthropic.claude-3")
        # Force the import inside ``_build_bedrock`` to fail by patching the
        # builtin import. We only need to intercept the specific module name.
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "langchain_aws":
                raise ImportError("simulated missing langchain_aws")
            return real_import(name, *args, **kwargs)

        with (
            patch.object(builtins, "__import__", side_effect=fake_import),
            pytest.raises(ImportError, match="langchain-aws"),
        ):
            build_chat_model(provider, model)


class TestChatModelFactoryCaching:
    def _providers(self) -> list[ProviderConfig]:
        return [
            ProviderConfig(
                id="p",
                base_url="https://x",
                api_key="k",
                models=[ModelConfig(id="m")],
            )
        ]

    def test_caches_instances(self) -> None:
        factory = ChatModelFactory(self._providers())
        from langchain_openai import ChatOpenAI

        cls = _get_reasoning_aware_chat_openai(ChatOpenAI)
        with patch.object(cls, "__init__", return_value=None) as mock_init:
            first = factory.get_chat_model("p/m")
            second = factory.get_chat_model("p/m")
        assert first is second
        assert mock_init.call_count == 1

    def test_unknown_provider_raises(self) -> None:
        factory = ChatModelFactory(self._providers())
        with pytest.raises(ValueError, match="Unknown provider"):
            factory.get_chat_model("other/m")

    def test_unknown_model_raises(self) -> None:
        factory = ChatModelFactory(self._providers())
        with pytest.raises(ValueError, match=r"not found or disabled"):
            factory.get_chat_model("p/nonexistent")

    def test_accepts_list_directly(self) -> None:
        """Factory must accept list[ProviderConfig], not HarnessAgentConfig."""
        providers = self._providers()
        factory = ChatModelFactory(providers)
        assert factory is not None


class TestReasoningContentRoundTrip:
    """The DeepSeek thinking-mode bug: ``reasoning_content`` must round-trip.

    Upstream ``langchain-openai`` 1.x silently drops the field. Our subclass
    captures it on parse and re-emits it on serialize.
    """

    def _build(self) -> Any:
        provider = ProviderConfig(
            id="example",
            base_url="https://api.example.com/v1",
            api_key="sk-x",
            protocol="openai",
        )
        model = ModelConfig(id="thinking-model")
        return build_chat_model(provider, model)

    def test_create_chat_result_captures_reasoning_content(self) -> None:
        """A response with ``reasoning_content`` lands in ``additional_kwargs``."""
        from langchain_core.messages import AIMessage

        instance = self._build()
        response = {
            "id": "resp-1",
            "model": "thinking-model",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Beijing weather is sunny.",
                        "reasoning_content": "thinking aloud here",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        result = instance._create_chat_result(response)
        msg = result.generations[0].message
        assert isinstance(msg, AIMessage)
        assert msg.additional_kwargs.get("reasoning_content") == "thinking aloud here"

    def test_get_request_payload_re_emits_reasoning_content(self) -> None:
        """A round-tripped AIMessage must carry ``reasoning_content`` back out."""
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        instance = self._build()
        ai = AIMessage(
            content="",
            additional_kwargs={"reasoning_content": "thinking again"},
            tool_calls=[
                {
                    "name": "get_weather",
                    "args": {"city": "Beijing"},
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
        )
        messages = [
            HumanMessage(content="weather?"),
            ai,
            ToolMessage(content="sunny", tool_call_id="call_1"),
        ]
        payload = instance._get_request_payload(messages)

        # Find the assistant entry in the rebuilt messages list.
        assistants = [m for m in payload["messages"] if m.get("role") == "assistant"]
        assert len(assistants) == 1
        assert assistants[0]["reasoning_content"] == "thinking again"

    def test_payload_unchanged_when_reasoning_content_absent(self) -> None:
        """No ``reasoning_content`` injected for normal AIMessages."""
        from langchain_core.messages import AIMessage, HumanMessage

        instance = self._build()
        messages = [
            HumanMessage(content="hi"),
            AIMessage(content="hello"),
        ]
        payload = instance._get_request_payload(messages)
        assistants = [m for m in payload["messages"] if m.get("role") == "assistant"]
        assert len(assistants) == 1
        assert "reasoning_content" not in assistants[0]

    def test_create_chat_result_no_op_without_reasoning_content(self) -> None:
        """Standard OpenAI response shouldn't gain a phantom ``reasoning_content``."""
        from langchain_core.messages import AIMessage

        instance = self._build()
        response = {
            "id": "resp-2",
            "model": "thinking-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "hi"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        result = instance._create_chat_result(response)
        msg = result.generations[0].message
        assert isinstance(msg, AIMessage)
        assert "reasoning_content" not in msg.additional_kwargs

    def test_subclass_is_memoised(self) -> None:
        """The subclass is built once per process and reused."""
        from langchain_openai import ChatOpenAI

        first = _get_reasoning_aware_chat_openai(ChatOpenAI)
        second = _get_reasoning_aware_chat_openai(ChatOpenAI)
        assert first is second
        assert issubclass(first, ChatOpenAI)


class TestCodexResponses:
    @staticmethod
    def _build(
        base_url: str = "https://chatgpt.com/backend-api/codex", *, model_config: ModelConfig | None = None
    ) -> Any:
        return build_chat_model(
            ProviderConfig(
                id="openai-codex",
                protocol="openai",
                base_url=base_url,
                api_key="sk-test",
                headers={"ChatGPT-Account-Id": "test-account"},
            ),
            model_config or ModelConfig(id="gpt-5.5"),
        )

    @pytest.mark.asyncio
    async def test_codex_never_falls_back_to_chat_completions(self) -> None:
        from langchain_core.messages import HumanMessage
        from langchain_openai import ChatOpenAI

        instance = self._build(
            model_config=ModelConfig(id="gpt-5.5", api_mode="responses", api_fallback="chat_completions")
        )
        assert instance.use_responses_api is True
        assert getattr(instance, "_harness_api_fallback_model", None) is None
        error = TestResponsesApiFallback.UnsupportedEndpointError()
        with (
            patch.object(ChatOpenAI, "_agenerate", side_effect=error) as generate,
            pytest.raises(TestResponsesApiFallback.UnsupportedEndpointError),
        ):
            await instance._agenerate([HumanMessage(content="ping")])
        assert generate.call_count == 1

    def test_codex_overrides_default_api_mode_for_native_tool_search(self) -> None:
        instance = self._build(model_config=ModelConfig(id="gpt-5.5", native_tool_search=True))
        assert instance.use_responses_api is True
        assert instance._harness_native_tool_search is True

    def test_other_responses_endpoints_keep_their_instructions_behavior(self) -> None:
        instance = self._build(
            "https://api.example.com/v1", model_config=ModelConfig(id="gpt-5.5", api_mode="responses")
        )
        payload = instance._get_request_payload([("system", "Be concise."), ("human", "ping")])
        assert instance.use_responses_api is True
        assert "instructions" not in payload
        assert "store" not in payload
        assert payload["stream"] is False
        assert payload["input"][0]["content"] == "Be concise."

    @pytest.mark.parametrize("suffix", ["", "/"])
    def test_stateless_streaming_payload_and_headers(self, suffix: str) -> None:
        instance = self._build("https://chatgpt.com/backend-api/codex" + suffix)
        payload = instance._get_request_payload([("human", "ping")])
        assert payload["store"] is False
        assert payload["stream"] is True
        assert "input" in payload and "messages" not in payload
        assert instance.use_previous_response_id is False
        assert instance.output_version == "responses/v1"
        assert instance.default_headers["ChatGPT-Account-Id"] == "test-account"

    def test_system_and_tool_history_are_preserved_without_mutation(self) -> None:
        from copy import deepcopy

        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        history = [
            SystemMessage(content="Be concise."),
            HumanMessage(content="Echo hello."),
            AIMessage(
                content=[
                    {"type": "reasoning", "id": "rs_test", "summary": [], "encrypted_content": "opaque-test-reasoning"}
                ],
                tool_calls=[
                    {"name": "echo", "args": {"text": "hello"}, "id": "call_echo", "type": "tool_call"},
                ],
                response_metadata={"id": "resp_previous"},
            ),
            ToolMessage(content="hello", tool_call_id="call_echo"),
            SystemMessage(content="Keep the original instructions."),
            HumanMessage(content="Summarize the result."),
        ]
        before = deepcopy(history)
        payload = self._build()._get_request_payload(history)
        assert "previous_response_id" not in payload
        items = payload["input"]
        assert payload["instructions"] == "Be concise."
        assert [item["role"] for item in items if "role" in item] == ["user", "developer", "user"]
        assert next(item for item in items if item.get("role") == "developer")["content"] == (
            "Keep the original instructions."
        )
        call = next(item for item in items if item.get("type") == "function_call")
        result = next(item for item in items if item.get("type") == "function_call_output")
        assert call["call_id"] == result["call_id"] == "call_echo"
        assert result["output"] == "hello"
        reasoning = next(item for item in items if item.get("type") == "reasoning")
        assert reasoning["encrypted_content"] == "opaque-test-reasoning"
        assert history == before

    @pytest.mark.parametrize(
        "content, expected",
        [
            ("  Be concise.\n", "  Be concise.\n"),
            (
                [{"type": "text", "text": "Base rules."}, {"type": "text", "text": "Runtime rules."}],
                "Base rules.\n\nRuntime rules.",
            ),
        ],
    )
    def test_main_system_prompt_becomes_instructions(self, content: Any, expected: str) -> None:
        from copy import deepcopy

        from langchain_core.messages import HumanMessage, SystemMessage

        history = [SystemMessage(content=content), HumanMessage(content="ping")]
        before = deepcopy(history)
        payload = self._build()._get_request_payload(history)
        assert payload["instructions"] == expected
        assert [item["role"] for item in payload["input"]] == ["user"]
        assert history == before

    @pytest.mark.parametrize("explicit", ["Caller rules.", "", None])
    @pytest.mark.parametrize("via_extra_body", [False, True])
    def test_explicit_instructions_leave_system_messages_in_input(self, explicit: Any, via_extra_body: bool) -> None:
        options = {"instructions": explicit}
        if via_extra_body:
            options = {"extra_body": options}
        payload = self._build()._get_request_payload(
            [("system", "Main rules."), ("human", "ping"), ("system", "Later rules.")], **options
        )
        target = payload["extra_body"] if via_extra_body else payload
        assert "instructions" in target
        assert target["instructions"] == explicit
        if via_extra_body:
            assert "instructions" not in payload
        assert [item["role"] for item in payload["input"]] == ["developer", "user", "developer"]
        assert payload["input"][0]["content"] == "Main rules."
        assert payload["input"][2]["content"] == "Later rules."

    @pytest.mark.parametrize(
        "history, roles",
        [
            ([("human", "ping")], ["user"]),
            ([("developer", "Developer rules."), ("human", "ping")], ["developer", "user"]),
            ([("human", "ping"), ("system", "Later rules.")], ["user", "developer"]),
        ],
    )
    def test_no_main_system_prompt_keeps_message_roles(self, history: Any, roles: list[str]) -> None:
        payload = self._build()._get_request_payload(history)
        assert "instructions" not in payload
        assert [item["role"] for item in payload["input"]] == roles

    @pytest.mark.parametrize(
        "base_url",
        [
            "https://api.openai.com/v1",
            "https://chatgpt.com.example.org/backend-api/codex",
            "https://example.org/chatgpt.com/backend-api/codex",
            "https://chatgpt.com/backend-api/codex-other",
        ],
    )
    def test_other_endpoints_keep_chat_completions(self, base_url: str) -> None:
        instance = self._build(base_url)
        payload = instance._get_request_payload([("system", "Be concise."), ("human", "ping")])
        assert "messages" in payload and "input" not in payload
        assert payload["messages"][0]["role"] == "system"
        assert "store" not in payload
        assert payload["stream"] is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["ainvoke", "astream"])
    @pytest.mark.parametrize("bound_instructions", [False, True])
    async def test_http_request_and_sse_response(self, mode: str, bound_instructions: bool) -> None:
        import json

        import httpx
        from openai import AsyncOpenAI

        requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            body = json.loads(request.content)
            assert request.url.path == "/backend-api/codex/responses"
            assert request.headers["authorization"] == "Bearer sk-test"
            assert request.headers["chatgpt-account-id"] == "test-account"
            assert body["store"] is False
            assert body["stream"] is True
            if bound_instructions:
                assert body["instructions"] == "Caller rules."
                assert body["input"][0]["role"] == "developer"
                assert body["input"][0]["content"] == "Be concise."
            else:
                assert body["instructions"] == "Be concise."
                assert body["input"][0]["role"] == "user"
            assert "reasoning.encrypted_content" in body["include"]
            events = [
                {
                    "type": "response.output_text.delta",
                    "output_index": 0,
                    "content_index": 0,
                    "item_id": "msg_test",
                    "delta": "OK",
                },
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_test",
                        "object": "response",
                        "created_at": 0,
                        "model": "gpt-5.5",
                        "status": "completed",
                        "output": [],
                        "parallel_tool_calls": True,
                        "tool_choice": "auto",
                        "tools": [],
                    },
                },
            ]
            sse = "".join("data: " + json.dumps(event) + "\n\n" for event in events)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse)

        instance = self._build()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            instance.root_async_client = AsyncOpenAI(
                api_key="sk-test",
                base_url=instance.openai_api_base,
                default_headers=instance.default_headers,
                http_client=http,
            )
            messages = [("system", "Be concise."), ("human", "ping")]
            chat = instance.bind(instructions="Caller rules.") if bound_instructions else instance
            if mode == "ainvoke":
                result = await chat.ainvoke(messages)
                assert result.text == "OK"
            else:
                chunks = [chunk async for chunk in chat.astream(messages)]
                assert "".join(chunk.text for chunk in chunks) == "OK"
        assert len(requests) == 1

    def test_stateless_replay_does_not_reference_unstored_items(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        history = [
            HumanMessage(content="Say hello."),
            AIMessage(
                content=[
                    {"type": "text", "text": "Hello", "id": "msg_unstored"},
                    {"type": "reasoning", "id": "rs_unstored", "summary": []},
                ],
                response_metadata={"id": "resp_unstored"},
            ),
            HumanMessage(content="Repeat that."),
        ]
        payload = self._build()._get_request_payload(history)
        assert "previous_response_id" not in payload
        assistant = next(item for item in payload["input"] if item.get("role") == "assistant")
        assert "id" not in assistant
        assert assistant["content"][0]["text"] == "Hello"
        assert not any(item.get("type") == "reasoning" for item in payload["input"])


class TestResponsesApiFallback:
    class UnsupportedEndpointError(Exception):
        status_code = 404
        body = {"error": {"message": "Not Found"}}

    def _build(self) -> Any:
        provider = ProviderConfig(
            id="example",
            base_url="https://api.example.com/v1",
            api_key="sk-x",
            protocol="openai",
        )
        model = ModelConfig(
            id="responses-model",
            api_mode="responses",
            api_fallback="chat_completions",
        )
        return build_chat_model(provider, model)

    @pytest.mark.parametrize("status_code", [404, 405, 501])
    def test_endpoint_status_is_eligible(self, status_code: int) -> None:
        exc = self.UnsupportedEndpointError()
        exc.status_code = status_code
        assert _is_responses_api_unsupported_error(exc) is True

    @pytest.mark.parametrize("status_code", [401, 403, 429, 500, 503])
    def test_operational_error_is_not_eligible(self, status_code: int) -> None:
        exc = self.UnsupportedEndpointError()
        exc.status_code = status_code
        assert _is_responses_api_unsupported_error(exc) is False

    def test_explicit_unsupported_400_is_eligible(self) -> None:
        exc = self.UnsupportedEndpointError("This model does not support Responses API")
        exc.status_code = 400
        assert _is_responses_api_unsupported_error(exc) is True

    def test_generic_400_is_not_eligible(self) -> None:
        exc = self.UnsupportedEndpointError("invalid tool schema")
        exc.status_code = 400
        exc.body = {"error": {"message": "invalid tool schema"}}
        assert _is_responses_api_unsupported_error(exc) is False

    def test_non_streaming_call_falls_back_and_marks_result(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage
        from langchain_core.outputs import ChatGeneration, ChatResult
        from langchain_openai import ChatOpenAI

        instance = self._build()
        expected = ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])
        with patch.object(
            ChatOpenAI,
            "_generate",
            side_effect=[self.UnsupportedEndpointError(), expected],
        ) as generate:
            result = instance._generate([HumanMessage(content="ping")])

        assert generate.call_count == 2
        assert result.generations[0].message.response_metadata["api_fallback"] == "chat_completions"

    @pytest.mark.asyncio
    async def test_async_non_streaming_call_falls_back_and_marks_result(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage
        from langchain_core.outputs import ChatGeneration, ChatResult
        from langchain_openai import ChatOpenAI

        instance = self._build()
        expected = ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])
        calls = 0

        async def fake_agenerate(_model: Any, *_args: Any, **_kwargs: Any) -> ChatResult:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise self.UnsupportedEndpointError()
            return expected

        with patch.object(ChatOpenAI, "_agenerate", new=fake_agenerate):
            result = await instance._agenerate([HumanMessage(content="ping")])

        assert calls == 2
        assert result.generations[0].message.response_metadata["api_fallback"] == "chat_completions"

    def test_responses_only_request_option_disables_fallback(self) -> None:
        from langchain_core.messages import HumanMessage
        from langchain_openai import ChatOpenAI

        instance = self._build()
        with (
            patch.object(
                ChatOpenAI,
                "_generate",
                side_effect=self.UnsupportedEndpointError(),
            ) as generate,
            pytest.raises(self.UnsupportedEndpointError),
        ):
            instance._generate(
                [HumanMessage(content="ping")],
                previous_response_id="resp_123",
            )

        assert generate.call_count == 1

    def test_stream_falls_back_only_before_first_chunk(self) -> None:
        from langchain_core.messages import AIMessageChunk, HumanMessage
        from langchain_core.outputs import ChatGenerationChunk
        from langchain_openai import ChatOpenAI

        instance = self._build()

        def fake_stream(model: Any, *_args: Any, **_kwargs: Any) -> Any:
            if model.use_responses_api:
                raise self.UnsupportedEndpointError()
            yield ChatGenerationChunk(message=AIMessageChunk(content="ok"))

        with patch.object(ChatOpenAI, "_stream", new=fake_stream):
            chunks = list(instance._stream([HumanMessage(content="ping")]))

        assert len(chunks) == 1
        assert chunks[0].message.response_metadata["api_fallback"] == "chat_completions"

    def test_stream_does_not_fallback_after_first_chunk(self) -> None:
        from langchain_core.messages import AIMessageChunk, HumanMessage
        from langchain_core.outputs import ChatGenerationChunk
        from langchain_openai import ChatOpenAI

        instance = self._build()
        fallback_calls = 0

        def fake_stream(model: Any, *_args: Any, **_kwargs: Any) -> Any:
            nonlocal fallback_calls
            if model.use_responses_api:
                yield ChatGenerationChunk(message=AIMessageChunk(content="partial"))
                raise self.UnsupportedEndpointError()
            fallback_calls += 1
            yield ChatGenerationChunk(message=AIMessageChunk(content="duplicate"))

        with (
            patch.object(ChatOpenAI, "_stream", new=fake_stream),
            pytest.raises(self.UnsupportedEndpointError),
        ):
            list(instance._stream([HumanMessage(content="ping")]))

        assert fallback_calls == 0
