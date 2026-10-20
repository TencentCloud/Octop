"""MCPProtocol — MCP Sampling format adapter."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from octop_harness.protocols.langgraph import LangGraphProtocol


class MCPStreamWrapper:
    """Wraps a v3 stream object, providing .messages in MCP SamplingMessage format."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    @property
    def messages(self) -> AsyncGenerator[dict[str, Any], None]:
        return self._transform_messages()

    async def _transform_messages(self) -> AsyncGenerator[dict[str, Any], None]:
        async for message in self._inner.messages:
            async for token in message.text:
                yield {
                    "role": "assistant",
                    "content": {"type": "text", "text": token},
                    "model": "octop-harness",
                }

    @property
    def values(self) -> Any:
        return self._inner.values

    @property
    def output(self) -> Any:
        return self._inner.output

    @property
    def tool_calls(self) -> Any:
        return self._inner.tool_calls

    @property
    def subgraphs(self) -> Any:
        return self._inner.subgraphs


class MCPProtocol(LangGraphProtocol):
    """Adapts LangGraph output to MCP Sampling message format."""

    @property
    def name(self) -> str:
        """Human-readable protocol name."""
        return "mcp"

    async def call(self, messages: list[BaseMessage], config: dict[str, Any]) -> dict[str, Any]:
        """Execute a call and convert result to MCP CreateMessageResult format."""
        raw = await self._graph.ainvoke({"messages": messages}, config=config)
        return self._to_create_message_result(raw)

    async def stream(
        self, messages: list[Any], config: dict[str, Any], **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield public model text as MCP SamplingMessage dicts.

        Delegate graph projection to :class:`LangGraphProtocol` so nested
        internal model calls such as conversation summarization are filtered
        consistently before conversion to the MCP wire format.
        """
        async for event in super().stream(messages, config, **kwargs):
            if event.get("type") != "token":
                continue
            token = event.get("content", "")
            if not token:
                continue
            yield {
                "role": "assistant",
                "content": {"type": "text", "text": token},
                "model": "octop-harness",
            }

    async def stream_events(self, messages: list[Any], config: dict[str, Any], **kwargs: Any) -> Any:
        """Return an MCP-wrapped v3 stream object."""
        inner = await self._graph.astream_events({"messages": messages}, config=config, version="v3", **kwargs)
        return MCPStreamWrapper(inner)

    # ------------------------------------------------------------------
    # Endpoint methods for HTTP integration
    # ------------------------------------------------------------------

    async def create_message(self, request: dict[str, Any]) -> dict[str, Any]:
        """Accept an MCP CreateMessageRequest and return a CreateMessageResult dict."""
        messages, config = self._parse_mcp_request(request)
        return await self.call(messages, config)

    async def create_message_stream(self, request: dict[str, Any]) -> AsyncGenerator[dict[str, Any], None]:
        """Accept an MCP CreateMessageRequest and yield SamplingMessage dicts."""
        messages, config = self._parse_mcp_request(request)
        async for chunk in self.stream(messages, config):
            yield chunk

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_mcp_request(
        request: dict[str, Any],
    ) -> tuple[list[BaseMessage], dict[str, Any]]:
        """Convert MCP messages format to langchain BaseMessage list + config.

        MCP message format:
            {"role": "user"|"assistant", "content": {"type": "text", "text": "..."}}
        Content may also be a plain string.

        Model preferences are extracted from:
            request["modelPreferences"]["hints"][0]["name"]
        """
        messages: list[BaseMessage] = []
        for msg in request.get("messages", []):
            role = msg.get("role", "user")
            raw_content = msg.get("content", "")

            # Handle content as object or plain string
            text = raw_content.get("text", "") if isinstance(raw_content, dict) else str(raw_content)

            if role == "assistant":
                messages.append(AIMessage(content=text))
            else:
                messages.append(HumanMessage(content=text))

        config: dict[str, Any] = {}
        model_preferences = request.get("modelPreferences")
        if model_preferences is not None:
            hints = model_preferences.get("hints", [])
            if hints and hints[0].get("name"):
                config["configurable"] = {"model": hints[0]["name"]}

        return messages, config

    def _to_create_message_result(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Convert raw graph result to MCP CreateMessageResult format."""
        content = ""
        raw_messages = raw.get("messages", [])
        # Walk backwards to find the last AI message
        for msg in reversed(raw_messages):
            if isinstance(msg, BaseMessage):
                if "AI" in type(msg).__name__:
                    content = self._extract_content(msg.content)
                    break
            elif isinstance(msg, dict) and msg.get("role") == "assistant":
                content = msg.get("content", "")
                break

        return {
            "role": "assistant",
            "content": {"type": "text", "text": content},
            "model": "octop-harness",
            "stopReason": "endTurn",
        }

    @staticmethod
    def _extract_content(content: Any) -> str:
        """Extract text from message content (string or list format)."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            return "".join(text_parts)
        return ""
