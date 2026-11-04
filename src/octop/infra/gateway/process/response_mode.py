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
    "withhold_weixin_stream_preamble",
    "wrap_weixin_stream_processor",
]
