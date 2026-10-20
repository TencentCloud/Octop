"""OpenAIProtocol — ChatCompletion format adapter."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from octop_harness.protocols.langgraph import LangGraphProtocol


class OpenAIStreamWrapper:
    """Wraps a v3 stream object, providing .messages in ChatCompletionChunk format."""

    def __init__(self, inner: Any, completion_id: str, created: int) -> None:
        self._inner = inner
        self._completion_id = completion_id
        self._created = created

    @property
    def messages(self) -> AsyncGenerator[dict[str, Any], None]:
        """Yield ChatCompletionChunk dicts from inner stream messages."""
        return self._transform_messages()

    async def _transform_messages(self) -> AsyncGenerator[dict[str, Any], None]:
        async for message in self._inner.messages:
            # message.text is iterable for tokens
            async for token in message.text:
                yield {
                    "id": self._completion_id,
                    "object": "chat.completion.chunk",
                    "created": self._created,
                    "model": "octop-harness",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": token},
                            "finish_reason": None,
                        }
                    ],
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


class OpenAIProtocol(LangGraphProtocol):
    """Adapts LangGraph output to OpenAI ChatCompletion format."""

    @property
    def name(self) -> str:
        """Human-readable protocol name."""
        return "openai"

    async def call(self, messages: list[BaseMessage], config: dict[str, Any]) -> dict[str, Any]:
        """Execute a call and convert result to ChatCompletion format."""
        raw = await self._graph.ainvoke({"messages": messages}, config=config)
        return self._to_chat_completion(raw)

    async def stream(
        self, messages: list[Any], config: dict[str, Any], **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield public model text as ChatCompletionChunk dicts.

        Delegate graph projection to :class:`LangGraphProtocol` so nested
        internal model calls such as conversation summarization are filtered
        consistently before conversion to the OpenAI wire format.
        """
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        async for event in super().stream(messages, config, **kwargs):
            if event.get("type") != "token":
                continue
            token = event.get("content", "")
            if not token:
                continue
            yield {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": "octop-harness",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": token},
                        "finish_reason": None,
                    }
                ],
            }

    async def stream_events(self, messages: list[Any], config: dict[str, Any], **kwargs: Any) -> Any:
        """Return an OpenAI-wrapped v3 stream object."""
        inner = await self._graph.astream_events({"messages": messages}, config=config, version="v3", **kwargs)
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        return OpenAIStreamWrapper(inner, completion_id, created)

    # ------------------------------------------------------------------
    # Endpoint methods for HTTP integration
    # ------------------------------------------------------------------

    async def create_chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        """Accept an OpenAI request body and return a ChatCompletion dict."""
        messages, config = self._parse_openai_request(request)
        return await self.call(messages, config)

    async def create_chat_completion_stream(self, request: dict[str, Any]) -> AsyncGenerator[dict[str, Any], None]:
        """Accept an OpenAI request body and yield ChatCompletionChunk dicts."""
        messages, config = self._parse_openai_request(request)
        async for chunk in self.stream(messages, config):
            yield chunk

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_openai_request(request: dict[str, Any]) -> tuple[list[BaseMessage], dict[str, Any]]:
        """Convert OpenAI messages format to langchain BaseMessage list + config.

        Args:
            request: OpenAI-compatible request body with ``messages`` and
                optionally ``model``.

        Returns:
            A tuple of (messages, config).
        """
        role_map: dict[str, type[BaseMessage]] = {
            "system": SystemMessage,
            "user": HumanMessage,
            "assistant": AIMessage,
        }

        messages: list[BaseMessage] = []
        for msg in request.get("messages", []):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            cls = role_map.get(role, HumanMessage)
            messages.append(cls(content=content))

        config: dict[str, Any] = {}
        model = request.get("model")
        if model is not None:
            config["configurable"] = {"model": model}

        return messages, config

    def _to_chat_completion(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Convert raw graph result to ChatCompletion response.

        Extracts content from the last AI message in the graph result.
        """
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

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": "octop-harness",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
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
