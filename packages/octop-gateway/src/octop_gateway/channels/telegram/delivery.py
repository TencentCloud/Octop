"""Telegram delivery rules: explicit rejection retries, never ambiguous resends."""

from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from io import IOBase
from typing import Any

from telegram import InputFile, InputMedia
from telegram.error import BadRequest, RetryAfter, TelegramError


class RequestScheduler:
    """Schedule every SDK attempt independently of BaseChannel logical slots.

    Serialize admission at 30 requests/second per bot and one per second per
    chat. A full chat table waits for its oldest reservation to expire rather
    than evicting a live limit. Only one waiter holds the admission lock.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_chats: int = 1000,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._max_chats = max_chats
        self._lock = asyncio.Lock()
        self._bot_next = 0.0
        self._chats: OrderedDict[str, float] = OrderedDict()

    async def acquire(self, chat: Any = None) -> None:
        """Reserve one request; cancellation never reserves future slots."""
        async with self._lock:
            key = str(chat) if chat is not None else None
            while True:
                now = self._clock()
                while self._chats and next(iter(self._chats.values())) <= now:
                    self._chats.popitem(last=False)
                ready = max(self._bot_next, self._chats.get(key, 0.0) if key is not None else 0.0)
                if key is not None and key not in self._chats and len(self._chats) >= self._max_chats:
                    ready = max(ready, next(iter(self._chats.values())))
                if ready <= now:
                    break
                await self._sleep(ready - now)
            self._bot_next = now + 1 / 30
            if key is not None:
                self._chats[key] = now + 1
                self._chats.move_to_end(key)


@asynccontextmanager
async def sanitized_errors() -> AsyncIterator[None]:
    """Redact SDK errors while retaining their type and cancellation semantics."""
    try:
        yield
    except TelegramError as exc:
        exc.message = re.sub(r"https?://[^\s'\"<>]+", "[redacted URL]", str(exc))
        exc.message = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", "[redacted token]", exc.message)
        raise exc from None


def _upload_streams(value: Any) -> list[Any]:
    """Inspect PTB's actual upload storage, including album thumbnails/covers."""
    if isinstance(value, InputFile):
        content = value.input_file_content
        return [] if isinstance(content, bytes) else [content]
    if isinstance(value, InputMedia):
        return [
            stream for name in ("media", "thumbnail", "cover") for stream in _upload_streams(getattr(value, name, None))
        ]
    if isinstance(value, dict):
        return [stream for item in value.values() for stream in _upload_streams(item)]
    if isinstance(value, list | tuple):
        return [stream for item in value for stream in _upload_streams(item)]
    return [value] if isinstance(value, IOBase) else []


async def request(method: Any, *, scheduler: RequestScheduler | None = None, **kwargs: Any) -> Any:
    """Retry only explicit 429 rejections, with bounded attempts and delay."""
    # PTB consumes file objects while constructing multipart requests. An
    # explicit rejection is safe to retry only with the original upload bytes.
    uploads = []
    recoverable = True
    for stream in _upload_streams(kwargs):
        try:
            position = stream.tell()
            stream.seek(position)
        except (AttributeError, OSError, ValueError):
            recoverable = False
        else:
            uploads.append((stream, position))
    for attempt in range(3):
        try:
            if scheduler is not None:
                await scheduler.acquire(kwargs.get("chat_id"))
            async with sanitized_errors():
                return await method(**kwargs)
        except RetryAfter as exc:
            delay = exc.retry_after
            seconds = delay.total_seconds() if hasattr(delay, "total_seconds") else float(delay)
            if attempt == 2 or seconds > 30 or not recoverable:
                raise
            try:
                for stream, position in uploads:
                    stream.seek(position)
            except (AttributeError, OSError, ValueError):
                # Preserve the explicit rejection; never resend an empty upload.
                raise exc from None
            await asyncio.sleep(max(0, seconds))
    raise AssertionError("unreachable")


def formatting_error(exc: BadRequest) -> bool:
    """Only entity parsing failures permit a plaintext resend."""
    text = str(exc).lower()
    return any(
        marker in text for marker in ("parse entities", "unsupported start tag", "can't find end", "entity byte offset")
    )
