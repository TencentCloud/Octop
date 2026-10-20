"""Tests for ``octop_harness.protocols.base.ChatProtocol`` ABC."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
)

from octop_harness.protocols.base import ChatProtocol

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class ConcreteChatProtocol(ChatProtocol):
    """Minimal concrete implementation for testing."""

    @property
    def name(self) -> str:
        return "test-protocol"

    async def call(self, messages: list[BaseMessage], config: dict[str, Any]) -> dict[str, Any]:
        return await self._graph.ainvoke({"messages": messages}, config=config)

    async def stream(
        self, messages: list[BaseMessage], config: dict[str, Any], **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        stream_obj = await self._graph.astream_events({"messages": messages}, config=config, version="v3", **kwargs)
        async for message in stream_obj.messages:
            async for token in message.text:
                yield {"type": "token", "content": token}

    async def stream_events(self, messages: list[BaseMessage], config: dict[str, Any], **kwargs: Any) -> Any:
        return await self._graph.astream_events({"messages": messages}, config=config, version="v3", **kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChatProtocolABC:
    """Test that the ABC cannot be instantiated directly."""

    def test_cannot_instantiate_abc_directly(self) -> None:
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            ChatProtocol(graph=MagicMock())  # type: ignore[abstract]


class TestConcreteInstantiation:
    """Test that a concrete subclass instantiates correctly."""

    def test_concrete_subclass_holds_graph(self) -> None:
        fake_graph = MagicMock(name="fake-graph")
        protocol = ConcreteChatProtocol(graph=fake_graph)
        assert protocol._graph is fake_graph

    def test_name_property(self) -> None:
        protocol = ConcreteChatProtocol(graph=MagicMock())
        assert protocol.name == "test-protocol"


class TestCallDelegatesToGraph:
    """Test that call() delegates to the underlying graph."""

    @pytest.mark.asyncio
    async def test_call_delegates(self) -> None:
        fake_graph = MagicMock(name="fake-graph")
        expected = {"messages": [AIMessage(content="hello")]}
        fake_graph.ainvoke = AsyncMock(return_value=expected)

        protocol = ConcreteChatProtocol(graph=fake_graph)
        messages: list[BaseMessage] = [HumanMessage(content="hi")]
        config: dict[str, Any] = {"configurable": {"thread_id": "t1"}}

        result = await protocol.call(messages, config)

        assert result == expected
        fake_graph.ainvoke.assert_awaited_once_with({"messages": messages}, config=config)


class TestStreamEvents:
    """Test that stream_events() returns a v3 stream object."""

    @pytest.mark.asyncio
    async def test_stream_events_returns_v3_object(self) -> None:
        fake_stream = MagicMock(name="v3-stream")
        fake_graph = MagicMock(name="fake-graph")
        fake_graph.astream_events = AsyncMock(return_value=fake_stream)

        protocol = ConcreteChatProtocol(graph=fake_graph)
        messages: list[BaseMessage] = [HumanMessage(content="hi")]
        config: dict[str, Any] = {"configurable": {"thread_id": "t1"}}

        result = await protocol.stream_events(messages, config)

        assert result is fake_stream
        fake_graph.astream_events.assert_awaited_once_with({"messages": messages}, config=config, version="v3")
