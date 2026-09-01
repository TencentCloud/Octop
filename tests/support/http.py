"""WebSocket / streaming helpers for integration tests."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
from starlette.websockets import WebSocketDisconnect

# A single-loop session should never stall; the cap keeps a regression from
# wedging the whole suite instead of failing this one test.
_WS_RECEIVE_TIMEOUT_S = 20.0


def ws_token(auth: dict[str, str]) -> str:
    return auth["Authorization"].split(" ", 1)[1]


class ASGIWebSocketSession:
    """Drive an ASGI websocket endpoint on the caller's event loop.

    starlette's sync ``TestClient`` runs the app on its own anyio portal loop.
    That gives the process two loops over one ``OctopServer``, and loop-bound
    primitives shared by both (``AgentManager._lock``) then deadlock or raise
    "bound to a different event loop". Speaking ASGI directly keeps the
    handler, the gateway workers and the test on the same loop, exactly like
    uvicorn in production.
    """

    def __init__(self, app: Any, path: str) -> None:
        self._app = app
        self._path = path
        self._from_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._to_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    def _scope(self) -> dict[str, Any]:
        url = urlsplit(self._path)
        return {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": unquote(url.path),
            "raw_path": url.path.encode("ascii"),
            "query_string": url.query.encode("ascii"),
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "subprotocols": [],
            "state": {},
            "app": self._app,
        }

    async def _next_event(self, timeout: float) -> dict[str, Any]:
        assert self._task is not None
        getter: asyncio.Future[dict[str, Any]] = asyncio.ensure_future(self._from_app.get())
        done, _pending = await asyncio.wait(
            {getter, self._task},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if getter in done:
            return getter.result()
        getter.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await getter
        if self._task in done:
            # Surface a handler crash instead of a bare timeout.
            self._task.result()
            raise AssertionError("websocket handler returned without sending an event")
        raise TimeoutError(f"no websocket event after {timeout:.0f}s")

    async def connect(self, timeout: float = _WS_RECEIVE_TIMEOUT_S) -> None:
        self._task = asyncio.create_task(
            self._app(self._scope(), self._to_app.get, self._from_app.put),
            name=f"asgi-ws{self._path}",
        )
        await self._to_app.put({"type": "websocket.connect"})
        event = await self._next_event(timeout)
        if event["type"] == "websocket.close":
            raise WebSocketDisconnect(event.get("code", 1000), event.get("reason"))
        if event["type"] != "websocket.accept":
            raise AssertionError(f"unexpected handshake event: {event['type']}")

    async def send_json(self, payload: Any) -> None:
        await self._to_app.put(
            {"type": "websocket.receive", "text": json.dumps(payload, ensure_ascii=False)},
        )

    async def receive_json(self, *, timeout: float = _WS_RECEIVE_TIMEOUT_S) -> dict[str, Any]:
        event = await self._next_event(timeout)
        if event["type"] == "websocket.close":
            raise WebSocketDisconnect(event.get("code", 1000), event.get("reason"))
        raw = event.get("text")
        if raw is None:
            raw = bytes(event.get("bytes") or b"").decode("utf-8")
        parsed: dict[str, Any] = json.loads(raw)
        return parsed

    async def drain_turn(self, *, timeout: float = _WS_RECEIVE_TIMEOUT_S) -> list[dict[str, Any]]:
        """Collect frames until the turn reports ``done`` or ``error``."""
        chunks: list[dict[str, Any]] = []
        while True:
            chunk = await self.receive_json(timeout=timeout)
            chunks.append(chunk)
            if chunk.get("type") in ("done", "error"):
                return chunks

    async def close(self) -> None:
        if self._task is None:
            return
        task = self._task
        self._task = None
        await self._to_app.put({"type": "websocket.disconnect", "code": 1000})
        try:
            await asyncio.wait_for(task, timeout=_WS_RECEIVE_TIMEOUT_S)
        except (asyncio.CancelledError, TimeoutError):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


@asynccontextmanager
async def ws_connect(app: Any, path: str) -> AsyncIterator[ASGIWebSocketSession]:
    """Open an in-process websocket session against *app* on the current loop."""
    session = ASGIWebSocketSession(app, path)
    try:
        await session.connect()
        yield session
    finally:
        await session.close()


def chat_ws_path(agent_id: str, auth: dict[str, str]) -> str:
    return f"/api/agents/{agent_id}/chat/ws?token={ws_token(auth)}"


async def ws_chat_turn(
    client: httpx.AsyncClient,
    agent_id: str,
    auth: dict[str, str],
    *,
    mcp_servers: list[str] | None = None,
    text: str = "hi",
) -> list[dict[str, Any]]:
    body: dict[str, Any] = {
        "type": "user_turn",
        "text": text,
        "messages": [{"role": "user", "content": text}],
    }
    if mcp_servers is not None:
        body["mcp_servers"] = mcp_servers
    app = client._octop_app  # type: ignore[attr-defined]
    async with ws_connect(app, chat_ws_path(agent_id, auth)) as ws:
        await ws.send_json(body)
        return await ws.drain_turn()
