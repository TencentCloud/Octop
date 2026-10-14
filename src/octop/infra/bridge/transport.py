"""In-process Bridge WebSocket session — multiplex HTTP tunnel + turn frames."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import suppress
from typing import Any

logger = logging.getLogger(__name__)

SendText = Callable[[str], Awaitable[None]]
CloseTransport = Callable[[], Awaitable[None]]
TunnelHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
TurnHandler = Callable[[dict[str, Any]], Awaitable[None]]
BrowserHandler = Callable[[dict[str, Any]], Awaitable[None]]
JsonHandler = Callable[[dict[str, Any]], Awaitable[None]]

# One JSON frame (base64 body included). Keep the uvicorn server limit in sync.
BRIDGE_WS_MAX_BYTES = 32 * 1024 * 1024
# Raw bytes that still fit in one frame on a peer using uvicorn's 16MB default.
BRIDGE_TUNNEL_MAX_BODY_BYTES = 8 * 1024 * 1024
# Advertised when both sides can split an upload across several frames.
FEATURE_BODY_CHUNKS = "body_chunks"
ADVERTISED_BRIDGE_FEATURES = [FEATURE_BODY_CHUNKS]
# Each chunk stays well under the default WebSocket frame cap after base64.
BODY_CHUNK_RAW_BYTES = 256 * 1024
# Upper bound once ``body_chunks`` is negotiated. The peer upload route still
# enforces its own ``max_upload_mb``.
BRIDGE_TUNNEL_CHUNKED_MAX_BODY_BYTES = 100 * 1024 * 1024

# Application data frames reset NAT / L7 idle timers that ignore WS ping opcodes.
HEARTBEAT_INTERVAL_SEC = 20.0
# After this much silence *and* a peer that answers pong, drop the half-open link.
HEARTBEAT_TIMEOUT_SEC = 60.0


def _frame_body(payload: dict[str, Any]) -> bytes:
    raw = payload.get("body")
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    encoded = payload.get("body_b64")
    if not encoded:
        return b""
    return base64.b64decode(str(encoded))


def peer_feature_set(payload: dict[str, Any]) -> set[str]:
    """Feature names advertised on a hello / hello_ack frame."""
    raw = payload.get("features")
    if not isinstance(raw, list):
        return set()
    return {str(item) for item in raw if isinstance(item, str) and item.strip()}


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
        close_transport: CloseTransport | None = None,
        peer_features: set[str] | None = None,
    ) -> None:
        self.connection_id = connection_id
        self._send_text = send_text
        self._on_tunnel_request = on_tunnel_request
        self._on_turn_frame = on_turn_frame
        self._on_browser_frame = on_browser_frame
        self._on_raw = on_raw
        self._close_transport = close_transport
        self.peer_features = set(peer_features or ())
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._body_parts: dict[str, dict[str, Any]] = {}
        self._closed = asyncio.Event()
        self._lock = asyncio.Lock()
        self._last_recv = time.monotonic()
        self._seen_pong = False
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._bg_tasks: set[asyncio.Task[None]] = set()
        self.close_reason: str | None = None

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_recv

    def is_stale(self, *, timeout: float = HEARTBEAT_TIMEOUT_SEC) -> bool:
        """True when a pong-capable peer has gone silent (half-open / NAT drop)."""
        return self._seen_pong and self.idle_seconds() >= timeout

    async def wait_closed(self) -> None:
        await self._closed.wait()

    def start_heartbeat(
        self,
        *,
        interval: float = HEARTBEAT_INTERVAL_SEC,
        timeout: float = HEARTBEAT_TIMEOUT_SEC,
    ) -> None:
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            return
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(interval=interval, timeout=timeout),
            name=f"bridge-hb-{self.connection_id}",
        )

    async def _heartbeat_loop(self, *, interval: float, timeout: float) -> None:
        try:
            while not self.closed:
                await asyncio.sleep(interval)
                if self.closed:
                    return
                if self.is_stale(timeout=timeout):
                    logger.warning(
                        "bridge session %s heartbeat timeout idle=%.0fs",
                        self.connection_id,
                        self.idle_seconds(),
                    )
                    await self.close(reason="heartbeat timeout")
                    return
                try:
                    await self.send_json({"type": "ping"})
                except Exception:
                    await self.close(reason="heartbeat send failed")
                    return
        except asyncio.CancelledError:
            raise

    def _spawn(self, coro: Coroutine[Any, Any, None], *, name: str) -> None:
        task: asyncio.Task[None] = asyncio.create_task(coro, name=name)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def _note_recv(self) -> None:
        self._last_recv = time.monotonic()

    async def close(self, reason: str | None = None) -> None:
        if self._closed.is_set():
            return
        if reason and not self.close_reason:
            self.close_reason = reason
        self._closed.set()
        self._body_parts.clear()
        pending = list(self._pending.items())
        self._pending.clear()
        for _rid, fut in pending:
            if not fut.done():
                fut.set_exception(ConnectionError("bridge session closed"))
        hb = self._heartbeat_task
        self._heartbeat_task = None
        current = asyncio.current_task()
        if hb is not None and hb is not current and not hb.done():
            hb.cancel()
        for task in list(self._bg_tasks):
            if task is not current and not task.done():
                task.cancel()
        closer = self._close_transport
        self._close_transport = None
        if closer is not None:
            with suppress(Exception):
                await closer()

    async def send_json(self, payload: dict[str, Any]) -> None:
        if self.closed:
            raise ConnectionError("bridge session closed")
        try:
            await self._send_text(
                json.dumps(payload, ensure_ascii=False, default=bridge_json_default),
            )
        except Exception:
            await self.close(reason="send failed")
            raise

    async def handle_message(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("bridge session %s: non-JSON frame", self.connection_id)
            return
        if not isinstance(payload, dict):
            return
        self._note_recv()
        msg_type = str(payload.get("type") or "")
        if msg_type == "ping":
            await self.send_json({"type": "pong"})
            return
        if msg_type == "pong":
            self._seen_pong = True
            return
        if msg_type == "close":
            self.close_reason = str(payload.get("reason") or "").strip() or None
            await self.close()
            return
        if msg_type == "tunnel.request" and self._on_tunnel_request is not None:
            complete = self._ingest_body_frame(payload)
            if complete is None:
                return
            req_id = str(complete.get("id") or "")
            self._spawn(
                self._fulfill_tunnel_request(req_id, complete),
                name=f"bridge-tunnel-{req_id or 'unknown'}",
            )
            return
        if msg_type in {"tunnel.response", "tunnel.error"}:
            complete = payload if msg_type == "tunnel.error" else self._ingest_body_frame(payload)
            if complete is None:
                return
            req_id = str(complete.get("id") or "")
            fut = self._pending.pop(req_id, None)
            if fut is not None and not fut.done():
                fut.set_result(complete)
            return
        if msg_type.startswith("turn.") and self._on_turn_frame is not None:
            # turn.start can run for minutes — never block the recv / heartbeat loop.
            if msg_type == "turn.start":
                handler = self._on_turn_frame

                async def _run_turn() -> None:
                    await handler(payload)

                self._spawn(
                    _run_turn(),
                    name=f"bridge-turn-{payload.get('request_id') or 'unknown'}",
                )
                return
            await self._on_turn_frame(payload)
            return
        if msg_type.startswith("browser.") and self._on_browser_frame is not None:
            await self._on_browser_frame(payload)
            return
        if self._on_raw is not None:
            await self._on_raw(payload)

    async def _fulfill_tunnel_request(self, req_id: str, payload: dict[str, Any]) -> None:
        assert self._on_tunnel_request is not None
        try:
            result = await self._on_tunnel_request(payload)
            if self.closed:
                return
            body = _frame_body(result)
            fields = {
                k: v for k, v in result.items() if k not in {"body_b64", "body", "type", "id"}
            }
            await self._send_body_frames(
                frame_type="tunnel.response",
                req_id=req_id,
                fields=fields,
                body=body,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self.closed:
                return
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

    async def next_queue_item(
        self,
        queue: asyncio.Queue[dict[str, Any]],
        *,
        timeout: float,
    ) -> dict[str, Any]:
        """Wait for a multiplexed frame, aborting immediately if the WS dies."""
        if self.closed:
            raise ConnectionError("bridge session closed")
        get_task = asyncio.create_task(queue.get())
        closed_task = asyncio.create_task(self.wait_closed())
        try:
            done, pending = await asyncio.wait(
                {get_task, closed_task},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if get_task in done and not get_task.cancelled():
                return get_task.result()
            if self.closed or closed_task in done:
                raise ConnectionError("bridge session closed")
            raise TimeoutError("bridge session queue timeout")
        except asyncio.CancelledError:
            get_task.cancel()
            closed_task.cancel()
            raise

    def _ingest_body_frame(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Reassemble chunked tunnel bodies. ``None`` means more frames are coming."""
        more = bool(payload.get("body_more"))
        if "body_seq" not in payload and not more:
            return payload
        req_id = str(payload.get("id") or "")
        kind = str(payload.get("type") or "")
        key = f"{kind}:{req_id}"
        slot = self._body_parts.get(key)
        if slot is None:
            slot = {"meta": {}, "parts": {}}
            self._body_parts[key] = slot
        if not slot["meta"]:
            slot["meta"] = {
                k: v
                for k, v in payload.items()
                if k not in {"body_b64", "body", "body_seq", "body_more"}
            }
        seq = int(payload.get("body_seq") or 0)
        piece = _frame_body(payload)
        if piece:
            parts: dict[int, bytes] = slot["parts"]
            parts[seq] = piece
        if more:
            return None
        ordered = slot["parts"]
        body = b"".join(ordered[i] for i in sorted(ordered))
        self._body_parts.pop(key, None)
        merged = dict(slot["meta"])
        if body:
            merged["body_b64"] = base64.b64encode(body).decode("ascii")
        return merged

    def _chunk_body(self, body: bytes | None) -> bool:
        return bool(
            body and len(body) > BODY_CHUNK_RAW_BYTES and FEATURE_BODY_CHUNKS in self.peer_features
        )

    async def _send_body_frames(
        self,
        *,
        frame_type: str,
        req_id: str,
        fields: dict[str, Any],
        body: bytes | None,
    ) -> None:
        raw = body or b""
        if not self._chunk_body(raw):
            frame: dict[str, Any] = {"type": frame_type, "id": req_id, **fields}
            if raw:
                frame["body_b64"] = base64.b64encode(raw).decode("ascii")
            await self.send_json(frame)
            return
        offset = 0
        seq = 0
        total = len(raw)
        while offset < total:
            nxt = min(offset + BODY_CHUNK_RAW_BYTES, total)
            piece = raw[offset:nxt]
            frame = {
                "type": frame_type,
                "id": req_id,
                "body_seq": seq,
                "body_more": nxt < total,
                "body_b64": base64.b64encode(piece).decode("ascii"),
            }
            if seq == 0:
                frame.update(fields)
            seq += 1
            offset = nxt
            await self.send_json(frame)

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
        req_id = uuid.uuid4().hex
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        try:
            await self._send_body_frames(
                frame_type="tunnel.request",
                req_id=req_id,
                fields={
                    "method": method.upper(),
                    "path": path,
                    "query": query or "",
                    "headers": headers or {},
                },
                body=body,
            )
            return await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError as exc:
            self._pending.pop(req_id, None)
            if self.is_stale() or self.idle_seconds() >= HEARTBEAT_TIMEOUT_SEC:
                await self.close(reason="tunnel timeout")
            raise TimeoutError(f"bridge tunnel timeout id={req_id}") from exc
        except Exception:
            self._pending.pop(req_id, None)
            raise
