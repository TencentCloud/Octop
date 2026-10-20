"""Utility functions for content inspection, merging, and debouncing."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from octop_gateway.models import (
    AudioContent,
    ContentPart,
    ContentType,
    FileContent,
    ImageContent,
    InboundMessage,
    TextContent,
    VideoContent,
)

logger = logging.getLogger(__name__)
STREAM_CLOSE_TIMEOUT = 5.0


async def close_event_stream(stream: AsyncIterator[Any]) -> None:
    """Run an event producer's finalizers without waiting for another event.

    ERROR is terminal. Explicit close preserves host cleanup when the consumer
    stops at ERROR; a stalled finalizer is cancelled after five seconds. The
    caller must release local running/typing state in its own finally block.
    Iterators without an optional ``aclose`` need no explicit close.
    """
    close = getattr(stream, "aclose", None)
    if close is None:
        return
    try:
        async with asyncio.timeout(STREAM_CLOSE_TIMEOUT):
            await close()
    except TimeoutError:
        logger.warning("Event stream cleanup timed out")
    except Exception:
        logger.exception("Event stream cleanup failed")


_MEDIA_TYPES = frozenset({ContentType.IMAGE, ContentType.VIDEO, ContentType.AUDIO, ContentType.FILE})


# ---------------------------------------------------------------------------
# Content inspection helpers
# ---------------------------------------------------------------------------


def has_text(parts: list[ContentPart]) -> bool:
    """Return True if any part contains non-empty text."""
    return any(isinstance(p, TextContent) and p.text.strip() for p in parts)


def has_media(parts: list[ContentPart]) -> bool:
    """Return True if any part is a media type (image/video/audio/file)."""
    return any(p.type in _MEDIA_TYPES for p in parts)


def extract_text(parts: list[ContentPart]) -> str:
    """Concatenate all text content parts into a single string."""
    texts: list[str] = []
    for p in parts:
        if isinstance(p, TextContent) and p.text:
            texts.append(p.text)
    return "\n".join(texts)


def extract_media(parts: list[ContentPart]) -> list[ContentPart]:
    """Extract all media (non-text) content parts."""
    return [p for p in parts if p.type in _MEDIA_TYPES]


def get_media_url(part: ContentPart) -> str | None:
    """Get the URL from a media content part, or None for text."""
    if isinstance(part, ImageContent | VideoContent | AudioContent | FileContent):
        return part.url
    return None


# ---------------------------------------------------------------------------
# Message merging
# ---------------------------------------------------------------------------


def merge_messages(messages: list[InboundMessage]) -> InboundMessage:
    """Merge multiple inbound messages (same session) into one.

    Concatenates content parts, uses the first message's metadata as base,
    keeps the earliest timestamp.
    """
    if not messages:
        raise ValueError("Cannot merge empty message list")
    if len(messages) == 1:
        return messages[0]

    merged_content: list[ContentPart] = []
    merged_meta: dict[str, Any] = dict(messages[0].metadata)
    earliest_ts = messages[0].timestamp

    for msg in messages:
        merged_content.extend(msg.content)
        earliest_ts = min(earliest_ts, msg.timestamp)
        # Merge metadata (later messages may add keys)
        for k, v in msg.metadata.items():
            if k not in merged_meta:
                merged_meta[k] = v

    return messages[0].model_copy(
        update={
            "content": merged_content,
            "metadata": merged_meta,
            "timestamp": earliest_ts,
        }
    )


# ---------------------------------------------------------------------------
# Debouncer
# ---------------------------------------------------------------------------


class Debouncer:
    """Async debouncer: collects items under a key, flushes after delay.

    When items arrive for the same key within `delay` seconds, they are
    batched together. When the delay expires (or flush is called explicitly),
    the callback receives all accumulated items.
    """

    def __init__(
        self,
        delay: float,
        callback: Callable[[str, list[Any]], Awaitable[None]],
    ) -> None:
        self._delay = delay
        self._callback = callback
        self._buffers: dict[str, list[Any]] = {}
        self._timers: dict[str, asyncio.Task[None]] = {}

    async def add(self, key: str, item: Any) -> None:
        """Add an item to the debounce buffer for the given key."""
        self._buffers.setdefault(key, []).append(item)

        # Cancel existing timer and restart
        old_timer = self._timers.pop(key, None)
        if old_timer and not old_timer.done():
            old_timer.cancel()

        self._timers[key] = asyncio.create_task(self._delayed_flush(key))

    async def _delayed_flush(self, key: str) -> None:
        """Wait for delay then flush the buffer."""
        await asyncio.sleep(self._delay)
        await self.flush(key)

    async def flush(self, key: str) -> None:
        """Immediately flush all items for the given key."""
        items = self._buffers.pop(key, [])
        timer = self._timers.pop(key, None)
        if timer and not timer.done():
            timer.cancel()
        if items:
            try:
                await self._callback(key, items)
            except Exception:  # pylint: disable=broad-except
                # The callback is supplied by the host; isolate failures by debounce key.
                logger.exception("Debouncer callback failed for key=%s", key)

    async def flush_all(self) -> None:
        """Flush all pending buffers immediately."""
        keys = list(self._buffers.keys())
        for key in keys:
            await self.flush(key)

    @property
    def pending_keys(self) -> list[str]:
        """Return list of keys with pending items."""
        return [k for k, v in self._buffers.items() if v]
