"""Channel response delivery modes for external IM transports."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal

from octop_gateway.channel import MessageProcessor
from octop_gateway.models import (
    ContentPart,
    InboundMessage,
    MessageEvent,
    MessageEventType,
    TextContent,
)
from octop_gateway.utils import close_event_stream

from octop.infra.utils.llm_text import strip_thinking

ChannelResponseMode = Literal["invoke", "stream"]

DEFAULT_CHANNEL_RESPONSE_MODE: ChannelResponseMode = "invoke"


def normalize_channel_response_mode(value: Any) -> ChannelResponseMode:
    """Return a supported response mode, defaulting external IM to one-shot delivery."""
    if isinstance(value, str) and value.strip().lower() == "stream":
        return "stream"
    return DEFAULT_CHANNEL_RESPONSE_MODE


def _config_flag(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def qq_channel_response_mode(config: dict[str, Any]) -> ChannelResponseMode:
    """QQ C2C stream is on by default. Explicit ``c2c_streaming: false`` opts out."""
    if _config_flag(config.get("c2c_streaming"), default=True):
        return "stream"
    return "invoke"


async def withhold_pretool_stream_chunks(
    chunks: AsyncIterator[dict[str, Any]],
    *,
    keep_for_tools: frozenset[str] = frozenset({"ask_agent"}),
) -> AsyncIterator[dict[str, Any]]:
    """Withhold raw text until its tool batch or final-answer boundary is known.

    Only a batch consisting entirely of allowed tools keeps its lead-in text.
    Control/state chunks pass through unchanged, so consumers can still track
    usage and canonical checkpoint messages without accumulating discarded text.
    """
    pending: list[dict[str, Any]] = []
    call_names: dict[str, str] = {}
    call_ids: dict[str, str] = {}
    result_names: set[str] = set()
    seen_results: set[str] = set()
    saw_result = False

    def keep_pending() -> bool:
        names = set(call_names.values()) | result_names
        return not names or (saw_result and names <= keep_for_tools)

    try:
        async for chunk in chunks:
            kind = chunk.get("type")
            if kind in {"error", "hitl_required"}:
                pending.clear()
                yield chunk
                return

            if saw_result and kind in {"token", "delta", "tool_call_chunk"}:
                if keep_pending():
                    for held in pending:
                        yield held
                pending.clear()
                call_names.clear()
                call_ids.clear()
                result_names.clear()
                saw_result = False

            if kind in {"token", "delta"}:
                pending.append(chunk)
                continue

            if kind == "tool_call_chunk":
                call_id = str(chunk.get("id") or "")
                index = chunk.get("index")
                key = str(index) if index is not None else call_id or "0"
                call_names[key] = call_names.get(key, "") + str(chunk.get("name") or "")
                if call_id:
                    call_ids[call_id] = key
            elif kind == "tool_result":
                messages = chunk.get("messages")
                if isinstance(messages, list) and messages:
                    for message in messages:
                        if isinstance(message, dict):
                            call_id = str(message.get("tool_call_id") or "")
                            name = str(message.get("name") or "")
                            role = message.get("type") or message.get("role")
                        else:
                            call_id = str(getattr(message, "tool_call_id", None) or "")
                            name = str(getattr(message, "name", None) or "")
                            role = getattr(message, "type", None)
                        if not call_id and role != "tool":
                            continue
                        if call_id and (
                            call_id in seen_results or (call_ids and call_id not in call_ids)
                        ):
                            continue
                        if call_id:
                            seen_results.add(call_id)
                        result_key = call_ids.get(call_id)
                        if result_key is None and not call_ids and len(call_names) == 1:
                            result_key = next(iter(call_names))
                        if name:
                            result_names.add(name)
                            if result_key is not None:
                                call_names[result_key] = name
                        elif not call_names:
                            result_names.add("")  # An unknown tool cannot preserve narration.
                        saw_result = True
                else:
                    if chunk.get("name") or not call_names:
                        result_names.add(str(chunk.get("name") or ""))
                    saw_result = True
            yield chunk

        if keep_pending():
            for held in pending:
                yield held
    finally:
        await close_event_stream(chunks)


async def collapse_to_invoke_response(
    events: AsyncIterator[MessageEvent],
) -> AsyncIterator[MessageEvent]:
    """Collapse a streamed agent turn into one final user-visible response.

    The agent still runs through the streaming path, preserving cancellation,
    usage tracking, HITL, and tool media extraction. Text emitted before a tool
    call is treated as progress narration and discarded. The remaining final
    text and any generated media are delivered together when the turn completes.
    """
    text_buffer = ""
    media_buffer: list[ContentPart] = []

    try:
        async for event in events:
            if event.type == MessageEventType.DELTA:
                for part in event.content:
                    if isinstance(part, TextContent) and part.text:
                        text_buffer += part.text
                continue

            if event.type == MessageEventType.MESSAGE:
                for part in event.content:
                    if isinstance(part, TextContent):
                        text = part.text.strip()
                        if text:
                            if text_buffer and not text_buffer.endswith("\n"):
                                text_buffer += "\n"
                            text_buffer += text
                    else:
                        media_buffer.append(part)
                continue

            if event.type == MessageEventType.TOOL_START:
                # Assistant text immediately followed by a tool call is usually
                # progress narration. Keep it for ``ask_agent`` so team hosts still
                # show their dispatch line on invoke-mode channels.
                meta = event.metadata if isinstance(event.metadata, dict) else {}
                tool_key = str(meta.get("tool_key") or meta.get("tool_name") or "")
                if tool_key != "ask_agent":
                    text_buffer = ""
                continue

            if event.type in (
                MessageEventType.TYPING,
                MessageEventType.THINKING,
                MessageEventType.THINKING_DELTA,
                MessageEventType.FLUSH,
                MessageEventType.TOOL_END,
            ):
                continue

            if event.type == MessageEventType.ERROR:
                text_buffer = ""
                media_buffer.clear()
                yield event
                return

            if event.type == MessageEventType.COMPLETED:
                content: list[ContentPart] = []
                final_text = strip_thinking(text_buffer)
                if final_text:
                    content.append(TextContent(text=final_text))
                content.extend(media_buffer)
                if content:
                    yield MessageEvent(type=MessageEventType.MESSAGE, content=content)
                yield event
                return

            # Preserve future terminal/control events instead of silently losing them.
            yield event
    finally:
        await close_event_stream(events)


_WEIXIN_PREAMBLE_TYPES = frozenset(
    {
        MessageEventType.DELTA,
        MessageEventType.FLUSH,
        MessageEventType.THINKING,
        MessageEventType.THINKING_DELTA,
    }
)


def _weixin_tool_key(event: MessageEvent) -> str:
    meta = event.metadata if isinstance(event.metadata, dict) else {}
    return str(meta.get("tool_key") or meta.get("tool_name") or "")


def _drops_weixin_preamble(event: MessageEvent) -> bool:
    """Tool calls other than ``ask_agent`` discard the text that led into them."""
    return event.type == MessageEventType.TOOL_START and _weixin_tool_key(event) != "ask_agent"


async def withhold_weixin_stream_preamble(
    events: AsyncIterator[MessageEvent],
) -> AsyncIterator[MessageEvent]:
    """Drop text that is only the lead-in to a tool call.

    Used for WeChat team hosts, which stay on stream mode. Other channels are
    unchanged. ``ask_agent`` narration is kept so a team host can still say who
    it is calling. Media and the final answer pass through in their own order.
    """
    held: list[MessageEvent] = []
    try:
        async for event in events:
            if event.type in _WEIXIN_PREAMBLE_TYPES:
                held.append(event)
                continue
            if not _drops_weixin_preamble(event):
                for item in held:
                    yield item
            held.clear()
            yield event
            if event.type == MessageEventType.ERROR:
                return
        for item in held:
            yield item
    finally:
        await close_event_stream(events)


def wrap_weixin_stream_processor(processor: MessageProcessor) -> MessageProcessor:
    """Hide tool lead-in text before a WeChat stream processor emits it."""

    def _wrapped(message: InboundMessage) -> AsyncIterator[MessageEvent]:
        return withhold_weixin_stream_preamble(processor(message))

    return _wrapped


def processor_for_response_mode(
    processor: MessageProcessor,
    mode: ChannelResponseMode,
) -> MessageProcessor:
    """Wrap *processor* with invoke-style delivery when requested."""
    if mode == "stream":
        return processor

    def _invoke_processor(message: InboundMessage) -> AsyncIterator[MessageEvent]:
        return collapse_to_invoke_response(processor(message))

    return _invoke_processor


__all__ = [
    "ChannelResponseMode",
    "DEFAULT_CHANNEL_RESPONSE_MODE",
    "collapse_to_invoke_response",
    "normalize_channel_response_mode",
    "processor_for_response_mode",
    "qq_channel_response_mode",
    "withhold_pretool_stream_chunks",
    "withhold_weixin_stream_preamble",
    "wrap_weixin_stream_processor",
]
