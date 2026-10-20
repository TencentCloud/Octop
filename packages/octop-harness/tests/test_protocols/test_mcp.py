"""Tests for ``octop_harness.protocols.mcp.MCPProtocol``."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
)
from tests.test_protocols._fakes import (
    FakeMessage,
    FakeStream,
    collect_stream,
    graph_with_astream,
    public_model_stream_parts,
)

from octop_harness.protocols.mcp import MCPProtocol, MCPStreamWrapper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_protocol(graph: Any) -> MCPProtocol:
    """Create an MCPProtocol with the given graph mock."""
    return MCPProtocol(graph=graph)


# ---------------------------------------------------------------------------
# Tests: call
# ---------------------------------------------------------------------------


class TestCall:
    """Tests for MCPProtocol.call."""

    @pytest.mark.asyncio
    async def test_call_returns_create_message_result_format(self) -> None:
        """call() returns a dict with correct MCP CreateMessageResult structure."""
        graph = MagicMock()
        graph.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="Hello there!")]})

        protocol = _make_protocol(graph)
        result = await protocol.call([HumanMessage(content="hi")], {})

        assert result["role"] == "assistant"
        assert result["content"] == {"type": "text", "text": "Hello there!"}
        assert result["model"] == "octop-harness"
        assert result["stopReason"] == "endTurn"

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

        assert result["content"]["text"] == "final answer"


# ---------------------------------------------------------------------------
# Tests: stream / MCPStreamWrapper
# ---------------------------------------------------------------------------


class TestStream:
    """Tests for MCPProtocol.stream (yields MCP SamplingMessage dicts)."""

    @pytest.mark.asyncio
    async def test_stream_yields_sampling_message_dicts(self) -> None:
        """stream() yields MCP SamplingMessage dicts directly."""
        protocol = _make_protocol(graph_with_astream(public_model_stream_parts()))
        chunks = await collect_stream(protocol)

        assert len(chunks) == 2
        for c in chunks:
            assert c["role"] == "assistant"
            assert c["model"] == "octop-harness"
            assert c["content"]["type"] == "text"
        assert chunks[0]["content"]["text"] == "Hello"
        assert chunks[1]["content"]["text"] == " world"


class TestStreamEvents:
    """Tests for MCPProtocol.stream_events (returns MCPStreamWrapper)."""

    @pytest.mark.asyncio
    async def test_stream_events_returns_wrapper(self) -> None:
        """stream_events() returns an MCPStreamWrapper."""
        fake_stream = FakeStream([FakeMessage(["Hello"])])
        graph = MagicMock()
        graph.astream_events = AsyncMock(return_value=fake_stream)

        protocol = _make_protocol(graph)
        result = await protocol.stream_events([HumanMessage(content="hi")], {})

        assert isinstance(result, MCPStreamWrapper)

    @pytest.mark.asyncio
    async def test_wrapper_messages_yields_sampling_message_format(self) -> None:
        """MCPStreamWrapper.messages yields MCP SamplingMessage dicts."""
        fake_stream = FakeStream([FakeMessage(["Hello", " world"])])
        wrapper = MCPStreamWrapper(fake_stream)

        chunks: list[dict[str, Any]] = []
        async for chunk in wrapper.messages:
            chunks.append(chunk)

        assert len(chunks) == 2
        for c in chunks:
            assert c["role"] == "assistant"
            assert c["model"] == "octop-harness"
            assert c["content"]["type"] == "text"
            # SamplingMessage does NOT have stopReason
            assert "stopReason" not in c

        assert chunks[0]["content"]["text"] == "Hello"
        assert chunks[1]["content"]["text"] == " world"

    @pytest.mark.asyncio
    async def test_wrapper_passthrough_properties(self) -> None:
        """MCPStreamWrapper passes through values, output, tool_calls, subgraphs."""
        fake_stream = MagicMock()
        fake_stream.values = "mock_values"
        fake_stream.output = "mock_output"
        fake_stream.tool_calls = "mock_tool_calls"
        fake_stream.subgraphs = "mock_subgraphs"

        wrapper = MCPStreamWrapper(fake_stream)

        assert wrapper.values == "mock_values"
        assert wrapper.output == "mock_output"
        assert wrapper.tool_calls == "mock_tool_calls"
        assert wrapper.subgraphs == "mock_subgraphs"


# ---------------------------------------------------------------------------
# Tests: create_message
# ---------------------------------------------------------------------------


class TestCreateMessage:
    """Tests for MCPProtocol.create_message."""

    @pytest.mark.asyncio
    async def test_accepts_mcp_request_returns_create_message_result(self) -> None:
        """create_message() accepts MCP request body and returns CreateMessageResult."""
        graph = MagicMock()
        graph.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="response")]})

        protocol = _make_protocol(graph)
        request = {
            "messages": [
                {"role": "user", "content": {"type": "text", "text": "hello"}},
            ],
        }
        result = await protocol.create_message(request)

        assert result["role"] == "assistant"
        assert result["content"] == {"type": "text", "text": "response"}
        assert result["model"] == "octop-harness"
        assert result["stopReason"] == "endTurn"


# ---------------------------------------------------------------------------
# Tests: create_message_stream
# ---------------------------------------------------------------------------


class TestCreateMessageStream:
    """Tests for MCPProtocol.create_message_stream."""

    @pytest.mark.asyncio
    async def test_accepts_mcp_request_yields_sampling_messages(self) -> None:
        """create_message_stream() accepts MCP request body and yields SamplingMessages."""
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
        async for chunk in protocol.create_message_stream(request):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["role"] == "assistant"
        assert chunks[0]["content"] == {"type": "text", "text": "streamed"}
        assert chunks[0]["model"] == "octop-harness"


# ---------------------------------------------------------------------------
# Tests: _parse_mcp_request
# ---------------------------------------------------------------------------


class TestParseMcpRequest:
    """Tests for MCPProtocol._parse_mcp_request."""

    def test_converts_user_and_assistant_messages_with_content_object(self) -> None:
        """_parse_mcp_request converts MCP messages with content as dict."""
        request = {
            "messages": [
                {"role": "user", "content": {"type": "text", "text": "Hello"}},
                {"role": "assistant", "content": {"type": "text", "text": "Hi there"}},
            ]
        }

        messages, _config = MCPProtocol._parse_mcp_request(request)

        assert len(messages) == 2
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "Hello"
        assert isinstance(messages[1], AIMessage)
        assert messages[1].content == "Hi there"

    def test_handles_plain_string_content(self) -> None:
        """_parse_mcp_request handles content as a plain string."""
        request = {
            "messages": [
                {"role": "user", "content": "plain text message"},
                {"role": "assistant", "content": "assistant reply"},
            ]
        }

        messages, _config = MCPProtocol._parse_mcp_request(request)

        assert len(messages) == 2
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "plain text message"
        assert isinstance(messages[1], AIMessage)
        assert messages[1].content == "assistant reply"

    def test_extracts_model_from_model_preferences_hints(self) -> None:
        """_parse_mcp_request extracts model from modelPreferences.hints[0].name."""
        request = {
            "messages": [{"role": "user", "content": "hi"}],
            "modelPreferences": {
                "hints": [{"name": "claude-3-opus"}],
            },
        }

        messages, config = MCPProtocol._parse_mcp_request(request)

        assert config == {"configurable": {"model": "claude-3-opus"}}
        assert len(messages) == 1

    def test_no_model_preferences_returns_empty_config(self) -> None:
        """_parse_mcp_request returns empty config when no modelPreferences."""
        request = {
            "messages": [{"role": "user", "content": "hi"}],
        }

        _, config = MCPProtocol._parse_mcp_request(request)

        assert config == {}

    def test_empty_hints_returns_empty_config(self) -> None:
        """_parse_mcp_request returns empty config when hints list is empty."""
        request = {
            "messages": [{"role": "user", "content": "hi"}],
            "modelPreferences": {"hints": []},
        }

        _, config = MCPProtocol._parse_mcp_request(request)

        assert config == {}
