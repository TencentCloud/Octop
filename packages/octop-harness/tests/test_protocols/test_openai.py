"""Tests for ``octop_harness.protocols.openai.OpenAIProtocol``."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
)
from tests.test_protocols._fakes import (
    FakeMessage,
    FakeStream,
    collect_stream,
    graph_with_astream,
    public_model_stream_parts,
)

from octop_harness.protocols.openai import OpenAIProtocol, OpenAIStreamWrapper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_protocol(graph: Any) -> OpenAIProtocol:
    """Create an OpenAIProtocol with the given graph mock."""
    return OpenAIProtocol(graph=graph)


# ---------------------------------------------------------------------------
# Tests: call
# ---------------------------------------------------------------------------


class TestCall:
    """Tests for OpenAIProtocol.call."""

    @pytest.mark.asyncio
    async def test_call_returns_chat_completion_format(self) -> None:
        """call() returns a dict with correct ChatCompletion structure."""
        graph = MagicMock()
        graph.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="Hello there!")]})

        protocol = _make_protocol(graph)
        result = await protocol.call([HumanMessage(content="hi")], {})

        assert result["object"] == "chat.completion"
        assert result["model"] == "octop-harness"
        assert result["id"].startswith("chatcmpl-")
        assert len(result["id"]) == len("chatcmpl-") + 24
        assert isinstance(result["created"], int)
        assert len(result["choices"]) == 1
        choice = result["choices"][0]
        assert choice["index"] == 0
        assert choice["message"]["role"] == "assistant"
        assert choice["finish_reason"] == "stop"
        assert result["usage"] == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    @pytest.mark.asyncio
    async def test_call_extracts_content_from_last_ai_message(self) -> None:
        """call() extracts content from the last AI message in graph result."""
        graph = MagicMock()
        graph.ainvoke = AsyncMock(
            return_value={
                "messages": [
                    HumanMessage(content="question"),
                    AIMessage(content="first answer"),
                    HumanMessage(content="follow up"),
                    AIMessage(content="final answer"),
                ]
            }
        )

        protocol = _make_protocol(graph)
        result = await protocol.call([HumanMessage(content="hi")], {})

        assert result["choices"][0]["message"]["content"] == "final answer"

    @pytest.mark.asyncio
    async def test_call_handles_list_content(self) -> None:
        """call() extracts text from list-format content."""
        graph = MagicMock()
        graph.ainvoke = AsyncMock(
            return_value={
                "messages": [
                    AIMessage(content=[{"type": "text", "text": "block one"}, {"type": "text", "text": " block two"}])
                ]
            }
        )

        protocol = _make_protocol(graph)
        result = await protocol.call([HumanMessage(content="hi")], {})

        assert result["choices"][0]["message"]["content"] == "block one block two"


# ---------------------------------------------------------------------------
# Tests: stream / OpenAIStreamWrapper
# ---------------------------------------------------------------------------


class TestStream:
    """Tests for OpenAIProtocol.stream (yields ChatCompletionChunk dicts)."""

    @pytest.mark.asyncio
    async def test_stream_yields_chat_completion_chunks(self) -> None:
        """stream() yields ChatCompletionChunk dicts directly."""
        protocol = _make_protocol(graph_with_astream(public_model_stream_parts()))
        chunks = await collect_stream(protocol)

        assert len(chunks) == 2
        for c in chunks:
            assert c["object"] == "chat.completion.chunk"
            assert c["model"] == "octop-harness"
            assert c["choices"][0]["delta"]["role"] == "assistant"
        assert chunks[0]["choices"][0]["delta"]["content"] == "Hello"
        assert chunks[1]["choices"][0]["delta"]["content"] == " world"


class TestStreamEvents:
    """Tests for OpenAIProtocol.stream_events (returns OpenAIStreamWrapper)."""

    @pytest.mark.asyncio
    async def test_stream_events_returns_wrapper(self) -> None:
        """stream_events() returns an OpenAIStreamWrapper."""
        fake_stream = FakeStream([FakeMessage(["Hello"])])
        graph = MagicMock()
        graph.astream_events = AsyncMock(return_value=fake_stream)

        protocol = _make_protocol(graph)
        result = await protocol.stream_events([HumanMessage(content="hi")], {})

        assert isinstance(result, OpenAIStreamWrapper)

    @pytest.mark.asyncio
    async def test_wrapper_messages_yields_chat_completion_chunks(self) -> None:
        """OpenAIStreamWrapper.messages yields ChatCompletionChunk dicts."""
        fake_stream = FakeStream([FakeMessage(["Hello", " world"])])
        wrapper = OpenAIStreamWrapper(fake_stream, "chatcmpl-test123", 1700000000)

        chunks: list[dict[str, Any]] = []
        async for chunk in wrapper.messages:
            chunks.append(chunk)

        assert len(chunks) == 2
        for c in chunks:
            assert c["id"] == "chatcmpl-test123"
            assert c["object"] == "chat.completion.chunk"
            assert c["created"] == 1700000000
            assert c["model"] == "octop-harness"
            assert c["choices"][0]["index"] == 0
            assert c["choices"][0]["delta"]["role"] == "assistant"
            assert c["choices"][0]["finish_reason"] is None

        assert chunks[0]["choices"][0]["delta"]["content"] == "Hello"
        assert chunks[1]["choices"][0]["delta"]["content"] == " world"

    @pytest.mark.asyncio
    async def test_wrapper_shares_id_across_messages(self) -> None:
        """OpenAIStreamWrapper uses same id and created for all messages."""
        fake_stream = FakeStream(
            [
                FakeMessage(["part1"]),
                FakeMessage(["part2"]),
            ]
        )
        wrapper = OpenAIStreamWrapper(fake_stream, "chatcmpl-abc", 1700000000)

        chunks: list[dict[str, Any]] = []
        async for chunk in wrapper.messages:
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0]["id"] == chunks[1]["id"]
        assert chunks[0]["created"] == chunks[1]["created"]

    @pytest.mark.asyncio
    async def test_wrapper_passthrough_properties(self) -> None:
        """OpenAIStreamWrapper passes through values, output, tool_calls, subgraphs."""
        fake_stream = MagicMock()
        fake_stream.values = "mock_values"
        fake_stream.output = "mock_output"
        fake_stream.tool_calls = "mock_tool_calls"
        fake_stream.subgraphs = "mock_subgraphs"

        wrapper = OpenAIStreamWrapper(fake_stream, "id", 0)

        assert wrapper.values == "mock_values"
        assert wrapper.output == "mock_output"
        assert wrapper.tool_calls == "mock_tool_calls"
        assert wrapper.subgraphs == "mock_subgraphs"


# ---------------------------------------------------------------------------
# Tests: create_chat_completion
# ---------------------------------------------------------------------------


class TestCreateChatCompletion:
    """Tests for OpenAIProtocol.create_chat_completion."""

    @pytest.mark.asyncio
    async def test_accepts_openai_request_returns_chat_completion(self) -> None:
        """create_chat_completion() accepts OpenAI request body and returns ChatCompletion."""
        graph = MagicMock()
        graph.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="response")]})

        protocol = _make_protocol(graph)
        request = {
            "messages": [
                {"role": "user", "content": "hello"},
            ],
            "model": "gpt-4",
        }
        result = await protocol.create_chat_completion(request)

        assert result["object"] == "chat.completion"
        assert result["choices"][0]["message"]["content"] == "response"

    @pytest.mark.asyncio
    async def test_passes_model_in_config(self) -> None:
        """create_chat_completion() passes model from request into config."""
        graph = MagicMock()
        graph.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="ok")]})

        protocol = _make_protocol(graph)
        request = {
            "messages": [{"role": "user", "content": "hi"}],
            "model": "gpt-4o",
        }
        await protocol.create_chat_completion(request)

        # Verify ainvoke was called with config containing the model
        call_kwargs = graph.ainvoke.call_args
        config = call_kwargs.kwargs["config"]
        assert config["configurable"]["model"] == "gpt-4o"


# ---------------------------------------------------------------------------
# Tests: create_chat_completion_stream
# ---------------------------------------------------------------------------


class TestCreateChatCompletionStream:
    """Tests for OpenAIProtocol.create_chat_completion_stream."""

    @pytest.mark.asyncio
    async def test_accepts_openai_request_yields_chunks(self) -> None:
        """create_chat_completion_stream() accepts OpenAI request and yields chunks."""
        graph = graph_with_astream(
            [
                {
                    "type": "messages",
                    "data": (AIMessageChunk(content="streamed"), {"langgraph_node": "model"}),
                }
            ]
        )

        protocol = _make_protocol(graph)
        request = {
            "messages": [{"role": "user", "content": "hi"}],
        }

        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.create_chat_completion_stream(request):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["object"] == "chat.completion.chunk"
        assert chunks[0]["choices"][0]["delta"]["content"] == "streamed"


# ---------------------------------------------------------------------------
# Tests: _parse_openai_request
# ---------------------------------------------------------------------------


class TestParseOpenAIRequest:
    """Tests for OpenAIProtocol._parse_openai_request."""

    def test_converts_system_user_assistant_messages(self) -> None:
        """_parse_openai_request converts all three role types correctly."""
        request = {
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ]
        }

        messages, _config = OpenAIProtocol._parse_openai_request(request)

        assert len(messages) == 3
        assert isinstance(messages[0], SystemMessage)
        assert messages[0].content == "You are helpful."
        assert isinstance(messages[1], HumanMessage)
        assert messages[1].content == "Hello"
        assert isinstance(messages[2], AIMessage)
        assert messages[2].content == "Hi there"

    def test_extracts_model_to_config(self) -> None:
        """_parse_openai_request puts model in config['configurable']['model']."""
        request = {
            "messages": [{"role": "user", "content": "hi"}],
            "model": "gpt-4-turbo",
        }

        messages, config = OpenAIProtocol._parse_openai_request(request)

        assert config == {"configurable": {"model": "gpt-4-turbo"}}
        assert len(messages) == 1

    def test_no_model_returns_empty_config(self) -> None:
        """_parse_openai_request returns empty config when no model specified."""
        request = {
            "messages": [{"role": "user", "content": "hi"}],
        }

        _, config = OpenAIProtocol._parse_openai_request(request)

        assert config == {}

    def test_unknown_role_defaults_to_human_message(self) -> None:
        """_parse_openai_request defaults unknown roles to HumanMessage."""
        request = {
            "messages": [{"role": "function", "content": "result"}],
        }

        messages, _ = OpenAIProtocol._parse_openai_request(request)

        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "result"
