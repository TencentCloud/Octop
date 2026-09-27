"""Ref-counted embedded OctopServer for reuse within one asyncio event loop."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from octop.infra.server import OctopServer

_lock = asyncio.Lock()
_server: OctopServer | None = None
_refs = 0


@asynccontextmanager
async def embedded_runtime() -> AsyncIterator[OctopServer]:
    """Boot OctopServer once per event loop; nested ``async with`` shares it."""
    global _server, _refs

    async with _lock:
        if _server is None:
            _server = OctopServer(register_im_channels=False)
            await _server.start()
        _refs += 1
        server = _server

    try:
        yield server
    finally:
        async with _lock:
            _refs -= 1
            if _refs == 0 and _server is not None:
                await _server.stop()
                _server = None


@asynccontextmanager
async def embedded_chat_server() -> AsyncIterator[OctopServer]:
    """Alias for :func:`embedded_runtime` (one server per nested scope)."""
    async with embedded_runtime() as server:
        yield server
