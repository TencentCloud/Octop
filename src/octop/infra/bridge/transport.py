"""In-process Bridge WebSocket session — multiplex HTTP tunnel + turn frames."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

SendText = Callable[[str], Awaitable[None]]
TunnelHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
TurnHandler = Callable[[dict[str, Any]], Awaitable[None]]
BrowserHandler = Callable[[dict[str, Any]], Awaitable[None]]
JsonHandler = Callable[[dict[str, Any]], Awaitable[None]]


def bridge_json_default(obj: Any) -> Any:
    """Fallback for LangChain messages / Pydantic models in turn chunks.

    Mirrors dashboard WS ``json_chunk_default`` so peer ``turn.chunk`` frames
    that embed ``HumanMessage`` / ``AIMessage`` do not crash ``json.dumps``.
    Kept here (not imported from ``api/``) to respect infra → api boundaries.
    """
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass
    return repr(obj)


class BridgeSession:
    """One live Bridge WS for a ``connection_id``."""

    def __init__(
        self,
        *,
        connection_id: str,
        send_text: SendText,
        on_tunnel_request: TunnelHandler | None = None,
        on_turn_frame: TurnHandler | None = None,
        on_browser_frame: BrowserHandler | None = None,
        on_raw: JsonHandler | None = None,
    ) -> None:
        self.connection_id = connection_id
        self._send_text = send_text
        self._on_tunnel_request = on_tunnel_request
        self._on_turn_frame = on_turn_frame
        self._on_browser_frame = on_browser_frame
        self._on_raw = on_raw
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._handler_tasks: set[asyncio.Task[None]] = set()
        self._closed = asyncio.Event()
        self._lock = asyncio.Lock()
        self.close_reason: str | None = None

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    async def close(self) -> None:
        if self.closed:
            return
        self._closed.set()
        pending = list(self._pending.items())
        self._pending.clear()
        for _rid, fut in pending:
            if not fut.done():
                fut.set_exception(ConnectionError("bridge session closed"))
        current = asyncio.current_task()
        tasks = [task for task in self._handler_tasks if task is not current]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._handler_tasks.difference_update(tasks)

    async def wait_closed(self) -> None:
        await self._closed.wait()

    def _start_handler(self, handler: TurnHandler, payload: dict[str, Any]) -> None:
        async def run() -> None:
            await handler(payload)

        task = asyncio.create_task(run(), name=f"bridge-handler-{self.connection_id}")
        self._handler_tasks.add(task)
        task.add_done_callback(self._handler_done)

    def _handler_done(self, task: asyncio.Task[None]) -> None:
        self._handler_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("bridge session %s: handler failed", self.connection_id, exc_info=exc)

    async def send_json(self, payload: dict[str, Any]) -> None:
        await self._send_text(
            json.dumps(payload, ensure_ascii=False, default=bridge_json_default),
        )

    async def handle_message(self, raw: str) -> None:
        if self.closed:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("bridge session %s: non-JSON frame", self.connection_id)
            return
        if not isinstance(payload, dict):
            return
        msg_type = str(payload.get("type") or "")
        if msg_type == "close":
            self.close_reason = str(payload.get("reason") or "").strip() or None
            await self.close()
            return
        if msg_type == "tunnel.request" and self._on_tunnel_request is not None:
            self._start_handler(self._handle_tunnel_request, payload)
            return
        if msg_type in {"tunnel.response", "tunnel.error"}:
            req_id = str(payload.get("id") or "")
            fut = self._pending.pop(req_id, None)
            if fut is not None and not fut.done():
                fut.set_result(payload)
            return
        if msg_type.startswith("turn.") and self._on_turn_frame is not None:
            if msg_type == "turn.start":
                # Running a peer turn must not block the receive pump for its replies.
                self._start_handler(self._on_turn_frame, payload)
            else:
                await self._on_turn_frame(payload)
            return
        if msg_type.startswith("browser.") and self._on_browser_frame is not None:
            await self._on_browser_frame(payload)
            return
        if self._on_raw is not None:
            await self._on_raw(payload)

    async def _handle_tunnel_request(self, payload: dict[str, Any]) -> None:
        assert self._on_tunnel_request is not None
        req_id = str(payload.get("id") or "")
        try:
            result = await self._on_tunnel_request(payload)
            await self.send_json({"type": "tunnel.response", "id": req_id, **result})
        except Exception as exc:
            from octop.infra.errors import OctopError

            if isinstance(exc, OctopError):
                await self.send_json(
                    {
                        "type": "tunnel.error",
                        "id": req_id,
                        "code": exc.code.value,
                        "message": str(exc)[:500],
                    }
                )
            else:
                logger.exception("bridge tunnel request failed id=%s", req_id)
                await self.send_json(
                    {
                        "type": "tunnel.error",
                        "id": req_id,
                        "code": "TUNNEL_ERROR",
                        "message": str(exc)[:500],
                    }
                )

    async def tunnel_request(
        self,
        *,
        method: str,
        path: str,
        query: str = "",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        if self.closed:
            raise ConnectionError("bridge session closed")
        import uuid

        req_id = uuid.uuid4().hex
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        frame: dict[str, Any] = {
            "type": "tunnel.request",
            "id": req_id,
            "method": method.upper(),
            "path": path,
            "query": query or "",
            "headers": headers or {},
        }
        if body:
            frame["body_b64"] = base64.b64encode(body).decode("ascii")
        try:
            await self.send_json(frame)
            return await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError as exc:
            raise TimeoutError(f"bridge tunnel timeout id={req_id}") from exc
        finally:
            self._pending.pop(req_id, None)
