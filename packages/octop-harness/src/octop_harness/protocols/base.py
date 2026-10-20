"""ChatProtocol — abstract base class for chat protocol implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import BaseMessage


class ChatProtocol(ABC):
    """Abstract base class defining the contract for chat protocol implementations.

    Subclasses must implement :meth:`call` and :meth:`stream` to provide
    the specific interaction pattern (e.g. single-turn, multi-turn, agentic).
    """

    def __init__(self, *, graph: Any) -> None:
        self._graph: Any = graph

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable protocol name."""
        ...

    @abstractmethod
    async def call(self, messages: list[BaseMessage], config: dict[str, Any]) -> dict[str, Any]:
        """Execute a single non-streaming call through the graph."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[BaseMessage],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream protocol-formatted chunks from the graph.

        Yields dict chunks in the protocol's native format:
        - langgraph: raw event dicts from the graph
        - openai: ChatCompletionChunk dicts
        - mcp: MCP SamplingMessage dicts
        """
        ...
        yield {}  # pragma: no cover

    @abstractmethod
    async def stream_events(
        self,
        messages: list[BaseMessage],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        """Return a v3 stream object for structured event consumption.

        The returned object provides typed projections:
        - stream.messages — ChatModelStream per LLM call (.text, .reasoning, .tool_calls)
        - stream.values — state snapshots
        - stream.output — final state
        - stream.subgraphs — nested graph runs
        - stream.tool_calls — tool lifecycle (with ToolCallTransformer)

        Protocol adapters (OpenAI, MCP) may wrap this object to provide
        projections in their respective format.
        """
        ...
