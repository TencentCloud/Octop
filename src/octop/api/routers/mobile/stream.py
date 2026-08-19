"""WebSocket Remote Android stream — adb screencap + tap/swipe."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
from functools import partial
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from octop.api.deps import resolve_user_from_token
from octop.infra.mobile.adb import capture_jpeg_frame, find_adb, list_devices, swipe, tap
from octop.infra.mobile.setup import mobile_status
from octop.infra.users.identity import User
from octop.infra.users.permissions import user_has_permission
from octop.infra.utils.locale import resolve_request_locale

logger = logging.getLogger(__name__)

router = APIRouter()

_DEFAULT_FPS = 8.0
_MIN_QUALITY = 30
_MAX_QUALITY = 95
_MIN_FPS = 1.0
_MAX_FPS = 20.0
_CAPTURE_TIMEOUT_S = 8.0
_INPUT_TIMEOUT_S = 5.0
_START_TIMEOUT_S = 15.0


def _clamp_stream_params(quality: int, max_fps: float) -> tuple[int, float]:
    q = max(_MIN_QUALITY, min(_MAX_QUALITY, quality))
    fps = max(_MIN_FPS, min(_MAX_FPS, max_fps))
    return q, fps


async def _send_json(ws: WebSocket, payload: dict[str, Any]) -> None:
    if ws.application_state == WebSocketState.CONNECTED:
        await ws.send_text(json.dumps(payload))


def _canvas_to_device(
    raw_x: float,
    raw_y: float,
    *,
    canvas_width: int,
    canvas_height: int,
    frame_width: int,
    frame_height: int,
) -> tuple[int, int]:
    cw = canvas_width or frame_width
    ch = canvas_height or frame_height
    fw = frame_width or cw
    fh = frame_height or ch
    if cw <= 0 or ch <= 0:
        return int(raw_x), int(raw_y)
    x = int(raw_x * fw / cw)
    y = int(raw_y * fh / ch)
    return max(0, min(fw - 1, x)), max(0, min(fh - 1, y))


def _auth_token_from_start(start_msg: dict[str, Any], query_token: str | None) -> str | None:
    token = start_msg.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    if query_token and query_token.strip():
        return query_token.strip()
    return None


async def _stream_frames(
    ws: WebSocket,
    *,
    device: str,
    quality: int,
    max_fps: float,
    frame_dims: list[int],
) -> None:
    interval = 1.0 / max_fps
    adb = find_adb()
    while ws.application_state == WebSocketState.CONNECTED:
        loop = asyncio.get_running_loop()
        try:
            captured = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    partial(capture_jpeg_frame, device, quality=quality, adb=adb),
                ),
                timeout=_CAPTURE_TIMEOUT_S,
            )
        except TimeoutError:
            logger.warning("mobile capture timed out (device=%s)", device)
            await asyncio.sleep(interval)
            continue
        if captured is None:
            await asyncio.sleep(interval)
            continue
        jpeg, width, height = captured
        frame_dims[0] = width
        frame_dims[1] = height
        await _send_json(
            ws,
            {
                "type": "frame",
                "data": base64.b64encode(jpeg).decode("ascii"),
                "width": width,
                "height": height,
            },
        )
        await asyncio.sleep(interval)


async def _handle_input(
    ws: WebSocket,
    msg: dict[str, Any],
    *,
    device: str,
    frame_dims: list[int],
) -> None:
    t = msg.get("type")
    fw, fh = frame_dims[0], frame_dims[1]
    adb = find_adb()
    loop = asyncio.get_running_loop()

    if t in {"click", "mouseup"}:
        raw_x = float(msg.get("x") or 0)
        raw_y = float(msg.get("y") or 0)
        x, y = _canvas_to_device(
            raw_x,
            raw_y,
            canvas_width=int(msg.get("canvas_width") or fw),
            canvas_height=int(msg.get("canvas_height") or fh),
            frame_width=fw,
            frame_height=fh,
        )
        ok = await asyncio.wait_for(
            loop.run_in_executor(None, partial(tap, device, x, y, adb=adb)),
            timeout=_INPUT_TIMEOUT_S,
        )
        await _send_json(ws, {"type": "action_result", "action": "click", "ok": ok})
        return

    if t == "swipe":
        x1, y1 = _canvas_to_device(
            float(msg.get("x1") or 0),
            float(msg.get("y1") or 0),
            canvas_width=int(msg.get("canvas_width") or fw),
            canvas_height=int(msg.get("canvas_height") or fh),
            frame_width=fw,
            frame_height=fh,
        )
        x2, y2 = _canvas_to_device(
            float(msg.get("x2") or 0),
            float(msg.get("y2") or 0),
            canvas_width=int(msg.get("canvas_width") or fw),
            canvas_height=int(msg.get("canvas_height") or fh),
            frame_width=fw,
            frame_height=fh,
        )
        ok = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                partial(swipe, device, x1, y1, x2, y2, adb=adb),
            ),
            timeout=_INPUT_TIMEOUT_S,
        )
        await _send_json(ws, {"type": "action_result", "action": "swipe", "ok": ok})


@router.websocket("/mobile-stream/ws")
async def mobile_stream_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    server = websocket.app.state.octop_server
    locale = resolve_request_locale(websocket)
    status = mobile_status(server.services.config, locale=locale)
    if status.setup_state != "ready" or not status.ok:
        await websocket.close(code=4003, reason=status.reason or status.setup_state)
        return

    await websocket.accept()
    stream_task: asyncio.Task[None] | None = None
    frame_dims = [0, 0]

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=_START_TIMEOUT_S)
        start_msg = json.loads(raw)
        if start_msg.get("type") != "start":
            await _send_json(websocket, {"type": "error", "message": "expected start message"})
            return

        auth_token = _auth_token_from_start(start_msg, token)
        if not auth_token:
            await _send_json(
                websocket, {"type": "error", "code": "AUTH_FAILED", "message": "missing token"}
            )
            await websocket.close(code=4001, reason="missing token")
            return
        try:
            user: User = resolve_user_from_token(server, auth_token)
        except Exception as exc:
            await _send_json(
                websocket, {"type": "error", "code": "AUTH_FAILED", "message": str(exc)}
            )
            await websocket.close(code=4001, reason=f"auth failed: {exc}")
            return
        if not user_has_permission(user, "mobile"):
            await websocket.close(code=4003, reason="permission required")
            return

        device = str(start_msg.get("device") or status.selected_device or "")
        if not device:
            devices = list_devices()
            device = devices[0] if devices else ""
        if not device:
            await _send_json(websocket, {"type": "error", "message": "no adb device"})
            await websocket.close(code=4003, reason="no device")
            return

        quality, max_fps = _clamp_stream_params(
            int(start_msg.get("quality") or 80),
            float(start_msg.get("max_fps") or _DEFAULT_FPS),
        )

        stream_task = asyncio.create_task(
            _stream_frames(
                websocket,
                device=device,
                quality=quality,
                max_fps=max_fps,
                frame_dims=frame_dims,
            )
        )

        while True:
            msg_raw = await websocket.receive_text()
            msg = json.loads(msg_raw)
            if msg.get("type") == "stop":
                break
            await _handle_input(websocket, msg, device=device, frame_dims=frame_dims)
    except WebSocketDisconnect:
        pass
    except TimeoutError:
        with contextlib.suppress(Exception):
            await websocket.close(code=4008, reason="start timeout")
    except Exception:
        logger.exception("mobile stream failed")
    finally:
        if stream_task is not None and not stream_task.done():
            stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stream_task
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()
