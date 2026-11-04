"""Coalesce accept resource errors before asyncio formats repeated tracebacks."""

from __future__ import annotations

import asyncio
import errno
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

ACCEPT_ERROR_WINDOW_SECONDS = 10.0
_RESOURCE_ERRNOS = frozenset({errno.EMFILE, errno.ENFILE, errno.ENOBUFS, errno.ENOMEM})


@contextmanager
def coalesce_accept_errors(loop: asyncio.AbstractEventLoop) -> Iterator[None]:
    """Keep the first traceback per errno/window and summarize duplicates.

    CPython's accept loop may report the same exhaustion once per backlog
    slot before its delayed retry. Other loop exceptions retain their
    original handler, and pending summaries are flushed on shutdown.
    """
    previous = loop.get_exception_handler()
    counts: dict[int, int] = {}
    timers: dict[int, asyncio.TimerHandle] = {}

    def flush(code: int) -> None:
        timers.pop(code).cancel()
        suppressed = counts.pop(code)
        if suppressed:
            logger.warning(
                "Suppressed %s additional socket.accept() resource errors (errno=%s) within %.0fs",
                suppressed,
                code,
                ACCEPT_ERROR_WINDOW_SECONDS,
            )

    def handler(event_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exc = context.get("exception")
        if (
            context.get("message") == "socket.accept() out of system resource"
            and isinstance(exc, OSError)
            and exc.errno in _RESOURCE_ERRNOS
        ):
            code = exc.errno
            assert code is not None
            if code in counts:
                counts[code] += 1
                return
            counts[code] = 0
            timers[code] = loop.call_later(ACCEPT_ERROR_WINDOW_SECONDS, flush, code)
        if previous is None:
            event_loop.default_exception_handler(context)
        else:
            previous(event_loop, context)

    loop.set_exception_handler(handler)
    try:
        yield
    finally:
        if loop.get_exception_handler() is handler:
            loop.set_exception_handler(previous)
        for code in list(timers):
            flush(code)
