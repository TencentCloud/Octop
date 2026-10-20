"""Close nested event-stream iterators deterministically.

Gateway >= 1.0.3 ships ``octop_gateway.utils.close_event_stream``; installs
resolving only ``octop-gateway>=1.0.2`` get an equivalent fallback here.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)

_STREAM_CLOSE_TIMEOUT = 5.0

try:  # gateway >= 1.0.3
    from octop_gateway.utils import close_event_stream
except ImportError:

    async def close_event_stream(stream: AsyncIterator[Any]) -> None:
        """Run an event producer finalizers; a stalled one is cancelled."""
        close = getattr(stream, "aclose", None)
        if close is None:
            return
        try:
            async with asyncio.timeout(_STREAM_CLOSE_TIMEOUT):
                await close()
        except TimeoutError:
            logger.warning("Event stream cleanup timed out")
        except Exception:  # noqa: BLE001 cleanup must not break the sender
            logger.exception("Event stream cleanup failed")


__all__ = ["close_event_stream"]
