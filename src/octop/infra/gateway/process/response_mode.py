"""Channel response delivery modes for external IM transports."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal

from harness_gateway.channel import MessageProcessor
from harness_gateway.models import (
    ContentPart,
    InboundMessage,
    MessageEvent,
    MessageEventType,
    TextContent,
)

from octop.infra.utils.llm_text import is_silent_reply, strip_thinking

ChannelResponseMode = Literal["invoke", "stream"]

DEFAULT_CHANNEL_RESPONSE_MODE: ChannelResponseMode = "invoke"


def normalize_channel_response_mode(value: Any) -> ChannelResponseMode:
    """Return a supported response mode, defaulting external IM to one-shot delivery."""
    if isinstance(value, str) and value.strip().lower() == "stream":
        return "stream"
    return DEFAULT_CHANNEL_RESPONSE_MODE


async def collapse_to_invoke_response(
    events: AsyncIterator[MessageEvent],
) -> AsyncIterator[MessageEvent]:
    """Collapse a streamed agent turn into one final user-visible response.

    The agent still runs through the streaming path, preserving cancellation,
    usage tracking, HITL, and tool media extraction. Text emitted before a tool
    call is treated as progress narration and discarded. The remaining final
    text and any generated media are delivered together when the turn completes.
    A final text ending with a silent-output marker (NO_REPLY / SKIP, see
    ``is_silent_reply``) suppresses the whole delivery: no MESSAGE event is
    emitted and generated media is dropped with it.
    """
    text_buffer = ""
    media_buffer: list[ContentPart] = []

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
            # Assistant text immediately followed by a tool call is progress
            # narration, not the final answer shown to an IM user.
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
            continue

        if event.type == MessageEventType.COMPLETED:
            content: list[ContentPart] = []
            final_text = strip_thinking(text_buffer)
            if is_silent_reply(final_text):
                # Model requested silent output: drop the final text and any
                # generated media so the channel delivers nothing this turn.
                final_text = ""
                media_buffer.clear()
            if final_text:
                content.append(TextContent(text=final_text))
            content.extend(media_buffer)
            if content:
                yield MessageEvent(type=MessageEventType.MESSAGE, content=content)
            yield event
            return

        # Preserve future terminal/control events instead of silently losing them.
        yield event


def processor_for_response_mode(
    processor: MessageProcessor,
    mode: ChannelResponseMode,
) -> MessageProcessor:
    """Wrap *processor* with invoke-style delivery when requested."""
    if mode == "stream":
        # Stream mode intentionally bypasses silent-marker suppression: deltas
        # are delivered live, so a trailing NO_REPLY/SKIP cannot be withdrawn
        # and must pass through as plain text.
        return processor

    async def _invoke_processor(message: InboundMessage) -> AsyncIterator[MessageEvent]:
        async for event in collapse_to_invoke_response(processor(message)):
            yield event

    return _invoke_processor


__all__ = [
    "ChannelResponseMode",
    "DEFAULT_CHANNEL_RESPONSE_MODE",
    "collapse_to_invoke_response",
    "normalize_channel_response_mode",
    "processor_for_response_mode",
]
