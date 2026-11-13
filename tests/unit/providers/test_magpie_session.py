"""Session header isolation for the harness version Octop actually imports."""

from __future__ import annotations

import asyncio

import httpx
from octop_harness.llm.session_header import install_request_hook, session_header_scope


async def test_magpie_session_header_follows_the_active_thread() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.headers["X-Magpie-Session"]] = request.headers["user-agent"]
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, headers={"User-Agent": "Octop/test"})
    install_request_hook(client, "X-Magpie-Session")

    async def one(thread_id: str) -> None:
        with session_header_scope(thread_id):
            await client.post("http://127.0.0.1:3425/v1/chat/completions")

    await asyncio.gather(one("thread-a"), one("thread-b"))
    await client.aclose()
    assert seen == {"thread-a": "Octop/test", "thread-b": "Octop/test"}
