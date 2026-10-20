"""Tests for ``octop_harness.protocols.langgraph.LangGraphProtocol``."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage

from octop_harness.protocols.langgraph import LangGraphProtocol

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_protocol(graph: Any) -> LangGraphProtocol:
    """Create a LangGraphProtocol with the given graph mock."""
    return LangGraphProtocol(graph=graph)


# ---------------------------------------------------------------------------
# Tests: call
# ---------------------------------------------------------------------------


class TestCall:
    """Tests for LangGraphProtocol.call."""

    @pytest.mark.asyncio
    async def test_call_returns_graph_result(self) -> None:
        """call() returns the graph ainvoke result directly."""
        expected = {"messages": [{"role": "assistant", "content": "hi"}]}
        graph = MagicMock()
        graph.ainvoke = AsyncMock(return_value=expected)

        protocol = _make_protocol(graph)
        messages: list[BaseMessage] = [HumanMessage(content="hello")]
        config: dict[str, Any] = {"configurable": {"thread_id": "t1"}}

        result = await protocol.call(messages, config)

        assert result == expected

    @pytest.mark.asyncio
    async def test_call_passes_messages_wrapped_in_dict(self) -> None:
        """call() wraps messages in {\"messages\": ...} when calling ainvoke."""
        graph = MagicMock()
        graph.ainvoke = AsyncMock(return_value={})

        protocol = _make_protocol(graph)
        messages: list[BaseMessage] = [HumanMessage(content="test")]
        config: dict[str, Any] = {"configurable": {"thread_id": "t2"}}

        await protocol.call(messages, config)

        graph.ainvoke.assert_awaited_once_with({"messages": messages}, config=config)


# ---------------------------------------------------------------------------
# Tests: stream
# ---------------------------------------------------------------------------


class TestStream:
    """Tests for LangGraphProtocol.stream (yields Harness-formatted events)."""

    @staticmethod
    def _make_astream(parts: list[dict[str, Any]]) -> Any:
        """Build a mock graph.astream that yields StreamPart dicts."""

        async def _astream(*args: Any, **kwargs: Any) -> Any:
            for part in parts:
                yield part

        return _astream

    @pytest.mark.asyncio
    async def test_stream_yields_token_from_messages(self) -> None:
        """Messages mode AIMessageChunk.content → token event."""
        msg_chunk = MagicMock()
        msg_chunk.type = "AIMessageChunk"  # real AIMessageChunk.type value
        msg_chunk.content = "Hello"
        msg_chunk.additional_kwargs = {}
        msg_chunk.tool_call_chunks = []

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "messages", "data": (msg_chunk, {"langgraph_node": "agent"})},
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        assert {"type": "token", "content": "Hello", "node": "agent"} in chunks

    @pytest.mark.asyncio
    async def test_stream_skips_tool_message_content(self) -> None:
        """ToolMessage content must NOT appear as a token event."""
        tool_msg = MagicMock()
        tool_msg.type = "tool"
        tool_msg.content = "Search returned 5 results..."
        tool_msg.additional_kwargs = {}
        tool_msg.tool_call_chunks = []

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "messages", "data": (tool_msg, {"langgraph_node": "tools"})},
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        # No token events should be emitted for tool message content
        token_events = [c for c in chunks if c["type"] == "token"]
        assert token_events == []

    @pytest.mark.asyncio
    async def test_stream_skips_human_message(self) -> None:
        """HumanMessage must NOT appear as a token event."""
        human_msg = MagicMock()
        human_msg.type = "human"
        human_msg.content = "user said something"
        human_msg.additional_kwargs = {}
        human_msg.tool_call_chunks = []

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "messages", "data": (human_msg, {"langgraph_node": "agent"})},
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        token_events = [c for c in chunks if c["type"] == "token"]
        assert token_events == []

    @pytest.mark.asyncio
    async def test_stream_skips_internal_summarization_model_output(self) -> None:
        """Compaction LLM output must never become a public token or reasoning event."""
        summary_chunk = AIMessageChunk(
            content="INTERNAL SUMMARY",
            additional_kwargs={"reasoning_content": "internal reasoning"},
        )
        visible_chunk = AIMessageChunk(content="VISIBLE ANSWER")
        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {
                    "type": "messages",
                    "data": (
                        summary_chunk,
                        {"langgraph_node": "model", "lc_source": "summarization"},
                    ),
                },
                {
                    "type": "messages",
                    "data": (visible_chunk, {"langgraph_node": "model"}),
                },
            ]
        )

        protocol = _make_protocol(graph)
        chunks = [chunk async for chunk in protocol.stream([HumanMessage(content="hi")], {})]

        assert [chunk for chunk in chunks if chunk["type"] == "reasoning"] == []
        assert [chunk["content"] for chunk in chunks if chunk["type"] == "token"] == ["VISIBLE ANSWER"]

    @pytest.mark.asyncio
    async def test_real_deepagents_compaction_only_streams_final_answer(self) -> None:
        """Regression: a real summary call runs, but only the main answer is public."""
        from deepagents import create_deep_agent
        from deepagents.backends import StateBackend
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        class ToolCallingFakeModel(FakeListChatModel):
            def bind_tools(self, tools: Any, **kwargs: Any) -> ToolCallingFakeModel:
                del tools, kwargs
                return self

        model = ToolCallingFakeModel(responses=["INTERNAL_SUMMARY", "VISIBLE_FINAL", "UNEXPECTED_THIRD_CALL"])
        # 0.7.16+ counts tool schemas; 4000 + 10 turns still triggers
        # summarization without overflowing the post-compaction budget.
        object.__setattr__(model, "profile", {"max_input_tokens": 4000})
        graph = create_deep_agent(model=model, tools=[], backend=StateBackend())
        messages: list[BaseMessage] = []
        for _ in range(10):
            messages.extend(
                [
                    HumanMessage(content="old user " + ("x " * 80)),
                    AIMessage(content="old assistant " + ("y " * 80)),
                ]
            )
        messages.append(HumanMessage(content="current question"))

        protocol = _make_protocol(graph)
        chunks = [chunk async for chunk in protocol.stream(messages, {})]

        public_text = "".join(str(chunk["content"]) for chunk in chunks if chunk["type"] == "token")
        assert model.i == 2  # summary call + user-facing model call
        assert public_text == "VISIBLE_FINAL"
        assert "INTERNAL_SUMMARY" not in public_text

    @pytest.mark.asyncio
    async def test_stream_yields_reasoning(self) -> None:
        """Messages mode reasoning_content → reasoning event."""
        msg_chunk = MagicMock()
        msg_chunk.type = "AIMessageChunk"
        msg_chunk.content = ""
        msg_chunk.additional_kwargs = {"reasoning_content": "Let me think..."}
        msg_chunk.tool_call_chunks = []

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "messages", "data": (msg_chunk, {"langgraph_node": "agent"})},
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        assert {"type": "reasoning", "content": "Let me think...", "node": "agent"} in chunks

    @pytest.mark.asyncio
    async def test_stream_yields_normalized_usage_per_model_call(self) -> None:
        msg_chunk = AIMessageChunk(
            id="run-call-1",
            content="",
            usage_metadata={
                "input_tokens": 1_000,
                "output_tokens": 80,
                "total_tokens": 1_080,
            },
            response_metadata={
                "model_name": "deepseek-v4-pro",
                "token_usage": {
                    "prompt_tokens": 1_000,
                    "completion_tokens": 80,
                    "prompt_cache_hit_tokens": 700,
                },
            },
        )
        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {
                    "type": "messages",
                    "data": (msg_chunk, {"langgraph_node": "model"}),
                },
            ]
        )

        protocol = _make_protocol(graph)
        chunks = [chunk async for chunk in protocol.stream([HumanMessage(content="hi")], {})]

        assert chunks == [
            {
                "type": "usage",
                "call_id": "run-call-1",
                "model": "deepseek-v4-pro",
                "node": "model",
                "usage": {
                    "input_tokens": 1_000,
                    "uncached_input_tokens": 300,
                    "cache_read_tokens": 700,
                    "cache_write_tokens": 0,
                    "output_tokens": 80,
                    "reasoning_tokens": 0,
                    "total_tokens": 1_080,
                },
            }
        ]

    @pytest.mark.asyncio
    async def test_stream_yields_tool_call_chunks(self) -> None:
        """Messages mode tool_call_chunks → tool_call_chunk events."""
        msg_chunk = MagicMock()
        msg_chunk.type = "AIMessageChunk"
        msg_chunk.content = ""
        msg_chunk.additional_kwargs = {}
        msg_chunk.tool_call_chunks = [
            {"id": "tc1", "name": "search", "args": '{"q": "hello"}', "index": 0},
        ]

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "messages", "data": (msg_chunk, {"langgraph_node": "agent"})},
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        assert {
            "type": "tool_call_chunk",
            "id": "tc1",
            "name": "search",
            "args": '{"q": "hello"}',
            "index": 0,
            "node": "agent",
        } in chunks

    @pytest.mark.asyncio
    async def test_stream_yields_tool_result(self) -> None:
        """Updates mode with ToolMessage → tool_result event."""
        tool_msg = MagicMock()
        tool_msg.type = "tool"

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "updates", "data": {"tools": {"messages": [tool_msg]}}},
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "tool_result"
        assert chunks[0]["node"] == "tools"
        assert chunks[0]["messages"] == [tool_msg]

    @pytest.mark.asyncio
    async def test_stream_yields_tool_result_with_overwrite_messages(self) -> None:
        """Updates mode with Overwrite(messages) → tool_result event (LangGraph reducer bypass)."""
        from langgraph.types import Overwrite

        tool_msg = MagicMock()
        tool_msg.type = "tool"

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {
                    "type": "updates",
                    "data": {
                        "PatchToolCallsMiddleware.before_agent": {
                            "messages": Overwrite(value=[tool_msg]),
                        },
                    },
                },
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["type"] == "tool_result"
        assert chunks[0]["messages"] == [tool_msg]

    @pytest.mark.asyncio
    async def test_stream_yields_state_update(self) -> None:
        """Updates mode without ToolMessage → state_update event."""
        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "updates", "data": {"agent": {"messages": []}}},
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        assert chunks[0] == {"type": "state_update", "node": "agent", "data": {"messages": []}}

    @pytest.mark.asyncio
    async def test_stream_yields_state_snapshot(self) -> None:
        """Values mode → state_snapshot event."""
        state = {"messages": [], "topic": "test"}

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "values", "data": state},
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        assert chunks[0] == {"type": "state_snapshot", "data": state}

    @pytest.mark.asyncio
    async def test_stream_yields_custom_events(self) -> None:
        """Custom mode → custom event."""
        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "custom", "data": {"progress": 50}},
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        assert chunks[0] == {"type": "custom", "data": {"progress": 50}}

    @pytest.mark.asyncio
    async def test_stream_calls_astream_with_multi_mode(self) -> None:
        """stream() calls graph.astream with correct stream_mode and version."""
        captured: list[tuple[Any, ...]] = []
        captured_kwargs: list[dict[str, Any]] = []

        async def _spy_astream(*args: Any, **kwargs: Any) -> Any:
            captured.append(args)
            captured_kwargs.append(kwargs)
            return
            yield  # make it an async generator

        graph = MagicMock()
        graph.astream = _spy_astream

        protocol = _make_protocol(graph)
        messages: list[BaseMessage] = [HumanMessage(content="hi")]
        config: dict[str, Any] = {"configurable": {"thread_id": "t1"}}

        async for _ in protocol.stream(messages, config):
            pass

        assert len(captured) == 1
        assert captured[0] == ({"messages": messages},)
        assert captured_kwargs[0] == {
            "config": config,
            "stream_mode": ["values", "updates", "messages", "custom"],
            "version": "v2",
        }

    @pytest.mark.asyncio
    async def test_stream_splits_think_tags_to_reasoning(self) -> None:
        """Content with <think> tags is split into reasoning + token events."""
        # Simulate a model (DeepSeek-R1) that emits <think>...</think> inline.
        chunks = []
        for text in ["<think>", "Let me think", "</think>", "The answer is 42"]:
            msg = MagicMock()
            msg.type = "AIMessageChunk"
            msg.content = text
            msg.additional_kwargs = {}
            msg.tool_call_chunks = []
            chunks.append({"type": "messages", "data": (msg, {"langgraph_node": "agent"})})

        graph = MagicMock()
        graph.astream = self._make_astream(chunks)

        protocol = _make_protocol(graph)
        events: list[dict[str, Any]] = []
        async for event in protocol.stream([HumanMessage(content="hi")], {}):
            events.append(event)

        reasoning_events = [e for e in events if e["type"] == "reasoning"]
        token_events = [e for e in events if e["type"] == "token"]

        assert any("Let me think" in e["content"] for e in reasoning_events)
        assert any("The answer is 42" in e["content"] for e in token_events)

    @pytest.mark.asyncio
    async def test_stream_drains_buffered_think_content(self) -> None:
        """Unclosed <think> at end of stream is drained as reasoning."""
        msg = MagicMock()
        msg.type = "AIMessageChunk"
        msg.content = "<think>still thinking"
        msg.additional_kwargs = {}
        msg.tool_call_chunks = []

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "messages", "data": (msg, {"langgraph_node": "agent"})},
            ]
        )

        protocol = _make_protocol(graph)
        events: list[dict[str, Any]] = []
        async for event in protocol.stream([HumanMessage(content="hi")], {}):
            events.append(event)

        # The drain should emit remaining buffer as reasoning
        reasoning_events = [e for e in events if e["type"] == "reasoning"]
        all_reasoning = "".join(e["content"] for e in reasoning_events)
        assert "still thinking" in all_reasoning

    @pytest.mark.asyncio
    async def test_stream_yields_events_from_content_blocks(self) -> None:
        """List content (thinking + text blocks) → reasoning + token events."""
        msg_chunk = MagicMock()
        msg_chunk.type = "AIMessageChunk"
        msg_chunk.content = [
            {"type": "thinking", "thinking": "weighing options"},
            {"type": "text", "text": "Here is the answer"},
        ]
        msg_chunk.additional_kwargs = {}
        msg_chunk.tool_call_chunks = []

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "messages", "data": (msg_chunk, {"langgraph_node": "agent"})},
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        assert {"type": "reasoning", "content": "weighing options", "node": "agent"} in chunks
        assert {"type": "token", "content": "Here is the answer", "node": "agent"} in chunks

    @pytest.mark.asyncio
    async def test_stream_skips_tool_use_content_blocks(self) -> None:
        """tool_use content blocks are skipped; sibling blocks still stream."""
        msg_chunk = MagicMock()
        msg_chunk.type = "AIMessageChunk"
        msg_chunk.content = [
            {"type": "tool_use", "id": "tu1", "name": "search", "input": {"q": "hi"}},
            {"type": "text", "text": "after the call"},
        ]
        msg_chunk.additional_kwargs = {}
        msg_chunk.tool_call_chunks = []

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "messages", "data": (msg_chunk, {"langgraph_node": "agent"})},
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        token_events = [c for c in chunks if c["type"] == "token"]
        assert token_events == [{"type": "token", "content": "after the call", "node": "agent"}]

    @pytest.mark.asyncio
    async def test_stream_str_content_unchanged(self) -> None:
        """Plain str content still streams as a single token event (regression)."""
        msg_chunk = MagicMock()
        msg_chunk.type = "AIMessageChunk"
        msg_chunk.content = "plain answer"
        msg_chunk.additional_kwargs = {}
        msg_chunk.tool_call_chunks = []

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {"type": "messages", "data": (msg_chunk, {"langgraph_node": "agent"})},
            ]
        )

        protocol = _make_protocol(graph)
        chunks: list[dict[str, Any]] = []
        async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
            chunks.append(chunk)

        assert chunks == [{"type": "token", "content": "plain answer", "node": "agent"}]

    @pytest.mark.asyncio
    async def test_stream_yields_hitl_required_on_interrupt(self) -> None:
        interrupt = MagicMock()
        interrupt.value = {
            "action_requests": [{"name": "bash", "args": {"command": "ls"}}],
            "review_configs": [{"action_name": "bash", "allowed_decisions": ["approve", "reject"]}],
        }

        graph = MagicMock()
        graph.astream = self._make_astream(
            [
                {
                    "type": "updates",
                    "data": {"__interrupt__": (interrupt,)},
                },
            ]
        )

        protocol = _make_protocol(graph)
        events: list[dict[str, Any]] = []
        async for event in protocol.stream([HumanMessage(content="hi")], {}):
            events.append(event)

        hitl = [e for e in events if e["type"] == "hitl_required"]
        assert len(hitl) == 1
        assert hitl[0]["request"]["action_requests"][0]["name"] == "bash"


class TestStreamEvents:
    """Tests for LangGraphProtocol.stream_events (returns v3 stream object)."""

    @pytest.mark.asyncio
    async def test_stream_events_returns_v3_stream_object(self) -> None:
        """stream_events() returns the raw v3 stream object."""
        fake_stream = MagicMock(name="v3-stream")
        graph = MagicMock()
        graph.astream_events = AsyncMock(return_value=fake_stream)

        protocol = _make_protocol(graph)
        messages: list[BaseMessage] = [HumanMessage(content="hi")]
        config: dict[str, Any] = {"configurable": {"thread_id": "t1"}}

        result = await protocol.stream_events(messages, config)

        assert result is fake_stream
        graph.astream_events.assert_awaited_once_with({"messages": messages}, config=config, version="v3")

    @pytest.mark.asyncio
    async def test_stream_events_passes_kwargs(self) -> None:
        """stream_events() forwards extra kwargs."""
        fake_stream = MagicMock(name="v3-stream")
        graph = MagicMock()
        graph.astream_events = AsyncMock(return_value=fake_stream)

        protocol = _make_protocol(graph)

        await protocol.stream_events([HumanMessage(content="hi")], {}, include_names=["agent"])

        graph.astream_events.assert_awaited_once_with(
            {"messages": [HumanMessage(content="hi")]}, config={}, version="v3", include_names=["agent"]
        )
