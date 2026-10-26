"""LangGraphProtocol — native LangGraph streaming protocol."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import aclosing
from enum import StrEnum
from typing import Any

from langchain_core.messages import BaseMessage
from langgraph.types import Command, Overwrite

from octop_harness.protocols.base import ChatProtocol
from octop_harness.protocols.think_splitter import ThinkSplitter
from octop_harness.usage import normalize_usage_metadata

_INTERNAL_LC_SOURCES = frozenset({"summarization"})


def _is_internal_model_stream(metadata: Any) -> bool:
    """Return whether a LangGraph message stream belongs to an internal LLM call.

    LangChain tags conversation-compaction calls with
    ``metadata["lc_source"] == "summarization"``.  LangGraph's ``messages``
    stream includes those nested model tokens alongside the user-facing model
    response, so they must be removed before protocol consumers see them.
    """
    return isinstance(metadata, dict) and metadata.get("lc_source") in _INTERNAL_LC_SOURCES


def _content_block_delta(block: Any) -> tuple[str, str]:
    """Split a streamed content block into (text, reasoning) delta parts."""
    if isinstance(block, str):
        return block, ""
    if not isinstance(block, dict):
        return "", ""
    block_type = block.get("type", "text")
    if block_type == "thinking":
        return "", str(block.get("thinking") or "")
    if block_type == "text":
        return str(block.get("text") or ""), ""
    return "", ""


def _emit_splitter_text(splitter: ThinkSplitter, text: str, node: str, out: list[dict[str, Any]]) -> None:
    final_text, thinking_text = splitter.feed(text)
    if thinking_text:
        out.append({"type": AgentEventType.REASONING, "content": thinking_text, "node": node})
    if final_text:
        out.append({"type": AgentEventType.TOKEN, "content": final_text, "node": node})


class AgentEventType(StrEnum):
    """Stream event types emitted by :meth:`~octop_harness.HarnessAgent.stream`."""

    TOKEN = "token"
    REASONING = "reasoning"
    TOOL_CALL_CHUNK = "tool_call_chunk"
    TOOL_RESULT = "tool_result"
    STATE_UPDATE = "state_update"
    STATE_SNAPSHOT = "state_snapshot"
    CUSTOM = "custom"
    HITL_REQUIRED = "hitl_required"
    USAGE = "usage"


def _serialize_hitl_request(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {"raw": str(value)}
    return {"raw": str(value)}


def _channel_messages(raw: Any) -> list[Any]:
    """Normalize a channel update to a message list.

    LangGraph nodes (and deepagents middleware such as ``PatchToolCallsMiddleware``)
    may emit ``Overwrite(value=[...])`` instead of a bare list for reducer bypass.
    """
    if isinstance(raw, Overwrite):
        raw = raw.value
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    return [raw]


def _usage_event(msg_chunk: Any, metadata: Any, node: str) -> dict[str, Any] | None:
    usage_metadata = getattr(msg_chunk, "usage_metadata", None)
    response_metadata = getattr(msg_chunk, "response_metadata", None)
    wire_usage: dict[str, Any] = {}
    if isinstance(response_metadata, dict):
        candidate = response_metadata.get("token_usage") or response_metadata.get("usage")
        if isinstance(candidate, dict):
            wire_usage = candidate
    normalized_source = {
        **wire_usage,
        **(usage_metadata if isinstance(usage_metadata, dict) else {}),
    }
    if not normalized_source:
        return None
    event: dict[str, Any] = {
        "type": AgentEventType.USAGE,
        "usage": normalize_usage_metadata(normalized_source),
        "node": node,
    }
    call_id = getattr(msg_chunk, "id", None)
    if not call_id and isinstance(metadata, dict):
        step = metadata.get("langgraph_step")
        if step is not None:
            call_id = f"{node or 'model'}:{step}"
    if isinstance(call_id, str) and call_id:
        event["call_id"] = call_id
    model = ""
    if isinstance(response_metadata, dict):
        model = str(response_metadata.get("model_name") or response_metadata.get("model") or "")
    if not model and isinstance(metadata, dict):
        model = str(metadata.get("ls_model_name") or metadata.get("model") or "")
    if model:
        event["model"] = model
    saved = _decision_saved(msg_chunk)
    if saved > 0:
        event["usage"] = {**event["usage"], "decision_saved": saved}
    return event


def _decision_saved(msg: Any) -> int:
    kwargs = getattr(msg, "additional_kwargs", None)
    if not isinstance(kwargs, dict) and isinstance(msg, dict):
        kwargs = msg.get("additional_kwargs")
    if not isinstance(kwargs, dict):
        return 0
    ctx = kwargs.get("context_usage")
    if not isinstance(ctx, dict):
        return 0
    try:
        saved = int(ctx.get("decision_saved") or 0)
    except (TypeError, ValueError):
        return 0
    return saved if saved > 0 else 0


class LangGraphProtocol(ChatProtocol):
    """Protocol implementation that passes calls directly to a LangGraph graph."""

    @property
    def name(self) -> str:
        return "langgraph"

    async def call(self, messages: list[BaseMessage], config: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = await self._graph.ainvoke({"messages": messages}, config=config)
        return result

    async def stream(
        self,
        messages: list[Any],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        splitter = ThinkSplitter()
        async with aclosing(
            self._graph.astream(
                {"messages": messages},
                config=config,
                stream_mode=["values", "updates", "messages", "custom"],
                version="v2",
                **kwargs,
            )
        ) as graph_chunks:
            async for chunk in graph_chunks:
                for event in self._project_chunk(chunk, splitter):
                    yield event
        for event in self._drain_splitter(splitter):
            yield event

    async def resume_stream(
        self,
        thread_id: str,
        decisions: list[dict[str, Any]],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        merged_config = dict(config)
        configurable = dict(merged_config.get("configurable") or {})
        configurable["thread_id"] = thread_id
        merged_config["configurable"] = configurable

        splitter = ThinkSplitter()
        async with aclosing(
            self._graph.astream(
                Command(resume={"decisions": decisions}),
                config=merged_config,
                stream_mode=["values", "updates", "messages", "custom"],
                version="v2",
                **kwargs,
            )
        ) as graph_chunks:
            async for chunk in graph_chunks:
                for event in self._project_chunk(chunk, splitter):
                    yield event
        for event in self._drain_splitter(splitter):
            yield event

    @staticmethod
    def _drain_splitter(splitter: ThinkSplitter) -> list[dict[str, Any]]:
        was_in_think = splitter.in_think
        leftover = splitter.drain()
        if not leftover:
            return []
        if was_in_think:
            return [{"type": AgentEventType.REASONING, "content": leftover, "node": ""}]
        return [{"type": AgentEventType.TOKEN, "content": leftover, "node": ""}]

    def _project_messages_chunk(self, data: Any, splitter: ThinkSplitter) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        msg_chunk, metadata = data
        if _is_internal_model_stream(metadata):
            return out
        node = metadata.get("langgraph_node", "")
        msg_type = getattr(msg_chunk, "type", "")
        if msg_type in ("tool", "human", "system"):
            return out
        reasoning = getattr(msg_chunk, "additional_kwargs", {}).get("reasoning_content")
        if reasoning:
            out.append({"type": AgentEventType.REASONING, "content": reasoning, "node": node})
        content = msg_chunk.content if hasattr(msg_chunk, "content") else ""
        if isinstance(content, list):
            # Anthropic / OpenAI-Responses streams deliver thinking and text as
            # content blocks, not a plain str.
            for block in content:
                block_text, block_reasoning = _content_block_delta(block)
                if block_reasoning:
                    out.append({"type": AgentEventType.REASONING, "content": block_reasoning, "node": node})
                if block_text:
                    _emit_splitter_text(splitter, block_text, node, out)
        elif content:
            _emit_splitter_text(splitter, content, node, out)
        for tc in getattr(msg_chunk, "tool_call_chunks", None) or []:
            out.append(
                {
                    "type": AgentEventType.TOOL_CALL_CHUNK,
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "args": tc.get("args", ""),
                    "index": tc.get("index", 0),
                    "node": node,
                }
            )
        usage_event = _usage_event(msg_chunk, metadata, node)
        if usage_event is not None:
            out.append(usage_event)
        return out

    def _project_updates_chunk(self, data: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if isinstance(data, dict) and "__interrupt__" in data:
            for item in data["__interrupt__"]:
                value = getattr(item, "value", item)
                out.append({"type": AgentEventType.HITL_REQUIRED, "request": _serialize_hitl_request(value)})
            return out
        for node_name, node_data in data.items():
            if node_name == "__interrupt__":
                continue
            node_messages = _channel_messages(node_data.get("messages")) if isinstance(node_data, dict) else []
            is_tool_result = any(
                getattr(m, "type", None) == "tool" or (isinstance(m, dict) and m.get("role") == "tool")
                for m in node_messages
            )
            if is_tool_result:
                out.append({"type": AgentEventType.TOOL_RESULT, "node": node_name, "messages": node_messages})
            else:
                out.append({"type": AgentEventType.STATE_UPDATE, "node": node_name, "data": node_data})
            for message in node_messages:
                if _decision_saved(message) <= 0:
                    continue
                usage_event = _usage_event(message, {}, node_name)
                if usage_event is not None:
                    out.append(usage_event)
        return out

    def _project_chunk(self, chunk: dict[str, Any], splitter: ThinkSplitter) -> list[dict[str, Any]]:
        event_type = chunk["type"]
        data = chunk["data"]
        if event_type == "messages":
            return self._project_messages_chunk(data, splitter)
        if event_type == "updates":
            return self._project_updates_chunk(data)
        if event_type == "values":
            return [{"type": AgentEventType.STATE_SNAPSHOT, "data": data}]
        if event_type == "custom":
            return [{"type": AgentEventType.CUSTOM, "data": data}]
        return []

    async def stream_events(
        self,
        messages: list[Any],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        return await self._graph.astream_events({"messages": messages}, config=config, version="v3", **kwargs)
