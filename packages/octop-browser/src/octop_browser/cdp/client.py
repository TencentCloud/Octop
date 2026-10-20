"""Pure asyncio Chrome DevTools Protocol WebSocket client."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any, Protocol

import websockets
from websockets.asyncio.client import ClientConnection

from octop_browser.settings import settings as _settings

logger = logging.getLogger(__name__)


class CDPSessionError(Exception):
    """Raised when a CDP command fails or the session is invalid."""


class ActivityTracker(Protocol):
    # pylint: disable=multiple-statements  # ruff format collapses stub bodies
    def activity_started(self) -> None: ...

    def activity_finished(self) -> None: ...


class CDPClient:
    """
    Manages a single CDP WebSocket connection to one browser page.

    Usage::

        client = CDPClient()
        await client.connect("ws://localhost:9222/devtools/page/ABC")
        result = await client.send("Page.navigate", {"url": "https://example.com"})
        await client.close()
    """

    def __init__(
        self,
        timeout: float | None = None,
        *,
        activity_tracker: ActivityTracker | None = None,
    ) -> None:
        self._timeout = timeout if timeout is not None else _settings.cdp_timeout
        self._activity_tracker = activity_tracker
        self._ws: ClientConnection | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._listeners: dict[str, list[Callable[..., Any]]] = {}
        self._recv_task: asyncio.Task[None] | None = None
        self._id = 0

    async def connect(self, ws_url: str) -> None:
        """Connect to a CDP WebSocket endpoint.

        ``websockets`` defaults to a 1 MiB receive frame cap; CDP responses
        for ``Page.captureScreenshot`` routinely exceed that on real-world
        pages (a base64 PNG of a 1440×900 viewport easily lands at 1.3-2 MiB).
        Hitting the cap closes the socket with code 1009 and the agent sees
        a confusing ``message too big`` error mid-action. Honor
        ``settings.cdp_max_message_size`` so screenshots up to that size
        come through cleanly.
        """
        ws = await websockets.connect(
            ws_url,
            max_size=_settings.cdp_max_message_size,
        )
        self._ws = ws
        self._recv_task = asyncio.create_task(self._recv_loop())
        logger.debug("CDP connected to %s", ws_url)

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        track_activity: bool = True,
    ) -> dict[str, Any]:
        """Send a CDP command and await its response."""
        if self._ws is None:
            raise CDPSessionError("Not connected")
        tracker = self._activity_tracker if track_activity else None
        if tracker is not None:
            tracker.activity_started()
        try:
            self._id += 1
            msg_id = self._id
            payload = json.dumps(
                {"id": msg_id, "method": method, "params": params or {}}
            )
            loop = asyncio.get_event_loop()
            future: asyncio.Future[dict[str, Any]] = loop.create_future()
            self._pending[msg_id] = future
            try:
                await self._ws.send(payload)
                result = await asyncio.wait_for(future, timeout=self._timeout)
            except asyncio.TimeoutError as exc:
                self._pending.pop(msg_id, None)
                raise CDPSessionError(
                    f"Timeout waiting for response to {method}"
                ) from exc
            except CDPSessionError:
                raise
            except Exception as exc:
                self._pending.pop(msg_id, None)
                raise CDPSessionError(f"CDP send failed for {method}: {exc}") from exc
        finally:
            if tracker is not None:
                tracker.activity_finished()
        if "error" in result:
            raise CDPSessionError(f"CDP error for {method}: {result['error']}")
        inner: dict[str, Any] = result.get("result", {})
        return inner

    async def send_passive(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send a health/status probe without extending the idle deadline."""
        return await self.send(method, params, track_activity=False)

    async def enable_domain(self, domain: str) -> None:
        """Enable a CDP domain (e.g. 'DOM', 'Page', 'Input')."""
        await self.send(f"{domain}.enable")

    def on(self, event: str, callback: Callable[..., Any]) -> None:
        """Register a listener for a CDP event."""
        self._listeners.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Callable[..., Any]) -> None:
        """Unregister a listener."""
        listeners = self._listeners.get(event, [])
        if callback in listeners:
            listeners.remove(callback)

    async def close(self) -> None:
        """Close the WebSocket connection."""
        ws = self._ws
        if ws:
            self._ws = None
            await ws.close()
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        logger.debug("CDP connection closed")

    async def _recv_loop(self) -> None:
        """Background task: read messages and dispatch to pending futures or
        listeners."""
        assert self._ws is not None
        try:
            async for raw in self._ws:
                msg: dict[str, Any] = json.loads(raw)
                if "id" in msg:
                    future = self._pending.pop(msg["id"], None)
                    if future and not future.done():
                        future.set_result(msg)
                elif "method" in msg:
                    method: str = msg["method"]
                    params: dict[str, Any] = msg.get("params", {})
                    callback_params = dict(params)
                    callback_params["__client"] = self
                    for cb in self._listeners.get(method, []):
                        result = cb(callback_params)
                        if asyncio.iscoroutine(result):
                            asyncio.create_task(result)
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
            logger.debug("CDP recv loop ended: %s", exc)
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(CDPSessionError(f"Connection lost: {exc}"))
            self._pending.clear()
