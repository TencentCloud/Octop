"""Shared fakes for protocol adapter tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from langchain_core.messages import AIMessageChunk, HumanMessage


def make_astream(parts: list[dict[str, Any]]) -> Any:
    async def _astream(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        for part in parts:
            yield part

    return _astream


class FakeMessage:
    """Simulates a v3 ChatModelStream message."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    @property
    def text(self) -> Any:
        return self._aiter_tokens()

    async def _aiter_tokens(self) -> Any:
        for t in self._tokens:
            yield t


class FakeStream:
    """Simulates a v3 stream object."""

    def __init__(self, messages: list[FakeMessage]) -> None:
        self._messages = messages

    @property
    def messages(self) -> Any:
        return self._aiter_messages()

    async def _aiter_messages(self) -> Any:
        for m in self._messages:
            yield m

    @property
    def values(self) -> Any:
        return None

    @property
    def output(self) -> Any:
        return None

    @property
    def tool_calls(self) -> Any:
        return None

    @property
    def subgraphs(self) -> Any:
        return None


def public_model_stream_parts() -> list[dict[str, Any]]:
    """One internal summarization chunk, then two public model tokens."""
    return [
        {
            "type": "messages",
            "data": (
                AIMessageChunk(content="INTERNAL"),
                {"langgraph_node": "model", "lc_source": "summarization"},
            ),
        },
        {
            "type": "messages",
            "data": (AIMessageChunk(content="Hello"), {"langgraph_node": "model"}),
        },
        {
            "type": "messages",
            "data": (AIMessageChunk(content=" world"), {"langgraph_node": "model"}),
        },
    ]


def graph_with_astream(parts: list[dict[str, Any]]) -> MagicMock:
    graph = MagicMock()
    graph.astream = make_astream(parts)
    return graph


async def collect_stream(protocol: Any) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    async for chunk in protocol.stream([HumanMessage(content="hi")], {}):
        chunks.append(chunk)
    return chunks
