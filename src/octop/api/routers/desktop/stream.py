"""WebSocket remote desktop stream — JPEG frames + OS input injection."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from functools import partial
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from octop.api.deps import resolve_user_from_token
from octop.infra.desktop.input import canvas_to_screen, run_desktop_action
from octop.infra.desktop.session import (
    DesktopSession,
    DesktopSessionLimitError,
    acquire_session,
    capture_executor,
    clear_user_stream,
    input_executor,
    release_session,
    supersede_user_stream,
)
from octop.infra.desktop.setup import desktop_status
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User
from octop.infra.utils.locale import resolve_request_locale

logger = logging.getLogger(__name__)

router = APIRouter()

_DEFAULT_FPS = 10
_MIN_QUALITY = 30
_MAX_QUALITY = 95
_MIN_FPS = 1.0
_MAX_FPS = 30.0
_CAPTURE_TIMEOUT_S = 5.0
_INPUT_TIMEOUT_S = 3.0
_START_TIMEOUT_S = 15.0


def _clamp_stream_params(quality: int, max_fps: float) -> tuple[int, float]:
    q = max(_MIN_QUALITY, min(_MAX_QUALITY, quality))
    fps = max(_MIN_FPS, min(_MAX_FPS, max_fps))
    return q, fps


async def _send_json(ws: WebSocket, payload: dict[str, Any]) -> None:
    if ws.application_state == WebSocketState.CONNECTED:
        await ws.send_text(json.dumps(payload))


def _resolve_display() -> str | None:
    status = desktop_status()
    if status.display:
        return status.display
    env_display = os.environ.get("DISPLAY", "").strip()
    return env_display or None


async def _run_input(action: Any) -> None:
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(input_executor(), action),
            timeout=_INPUT_TIMEOUT_S,
        )
    except TimeoutError:
        logger.warning("desktop input timed out")


async def _capture_frame(session: DesktopSession, quality: int) -> dict[str, Any] | None:
    loop = asyncio.get_running_loop()
    try:
        frame = await asyncio.wait_for(
            loop.run_in_executor(
                capture_executor(),
                partial(session.capture.capture_jpeg, quality=quality),
            ),
            timeout=_CAPTURE_TIMEOUT_S,
        )
    except TimeoutError:
        logger.warning("desktop capture timed out (display=%s)", session.display)
        return None
    if frame is None:
        return None
    return {
        "type": "frame",
        "data": frame.jpeg_b64,
        "width": frame.width,
        "height": frame.height,
    }


async def _stream_loop(
    ws: WebSocket,
    session: DesktopSession,
    *,
    quality: int,
    max_fps: float,
    frame_dims: list[int],
    locale: str,
) -> None:
    loop = asyncio.get_running_loop()
    monitors = await loop.run_in_executor(
        capture_executor(),
        session.capture.list_monitors,
    )
    await _send_json(ws, {"type": "display", "monitors": monitors})

    interval = 1.0 / max(max_fps, 1.0)
    miss_streak = 0
    while ws.application_state == WebSocketState.CONNECTED:
        loop_start = loop.time()
        payload = await _capture_frame(session, quality)
        if payload:
            miss_streak = 0
            frame_dims[0] = int(payload["width"])
            frame_dims[1] = int(payload["height"])
            await _send_json(ws, payload)
        else:
            miss_streak += 1
            if miss_streak == 1:
                logger.warning("desktop capture returned no frame (display=%s)", session.display)
            if miss_streak >= 30:
                err = OctopError.localized(ErrorCode.DESKTOP_CAPTURE_FAILED, locale)
                await _send_json(
                    ws,
                    {
                        "type": "error",
                        "code": err.code.value,
                        "message": err.message,
                    },
                )
                break
        elapsed = loop.time() - loop_start
        await asyncio.sleep(max(0.0, interval - elapsed))


async def _handle_input(
    ws: WebSocket,
    session: DesktopSession,
    msg: dict[str, Any],
    *,
    frame_width: int,
    frame_height: int,
) -> None:
    t = msg.get("type")
    if t == "desktop_action":
        action = str(msg.get("action") or "")
        if action:
            loop = asyncio.get_running_loop()
            ok = await loop.run_in_executor(
                input_executor(),
                partial(
                    run_desktop_action, action, display=session.display, injector=session.input
                ),
            )
            await _send_json(ws, {"type": "action_result", "action": action, "ok": ok})
        return

    if t not in {
        "click",
        "dblclick",
        "mousedown",
        "mouseup",
        "mousemove",
        "scroll",
        "type",
        "keydown",
        "keyup",
    }:
        return

    raw_x = float(msg.get("x") or 0)
    raw_y = float(msg.get("y") or 0)
    cw = int(msg.get("canvas_width") or frame_width or 0)
    ch = int(msg.get("canvas_height") or frame_height or 0)
    sw = int(msg.get("screen_width") or frame_width or 0)
    sh = int(msg.get("screen_height") or frame_height or 0)
    x, y = canvas_to_screen(
        raw_x,
        raw_y,
        canvas_width=cw or sw,
        canvas_height=ch or sh,
        screen_width=sw or cw,
        screen_height=sh or ch,
    )
    button = str(msg.get("button") or "left")
    inj = session.input

    if t == "click":
        await _run_input(partial(inj.click, x, y, button=button))
    elif t == "dblclick":
        await _run_input(partial(inj.click, x, y, button=button, clicks=2))
    elif t == "mousedown":
        await _run_input(partial(inj.mouse_down, x, y, button=button))
    elif t == "mouseup":
        await _run_input(partial(inj.mouse_up, x, y, button=button))
    elif t == "mousemove":
        await _run_input(partial(inj.mouse_move, x, y))
    elif t == "scroll":
        delta_x = float(msg.get("delta_x") or msg.get("deltaX") or 0)
        delta_y = float(msg.get("delta_y") or msg.get("deltaY") or 0)
        await _run_input(partial(inj.scroll, x, y, delta_x=delta_x, delta_y=delta_y))
    elif t == "type":
        text = str(msg.get("text") or "")
        if text:
            await _run_input(partial(inj.type_text, text))
    elif t == "keydown":
        key = str(msg.get("key") or "")
        if key:
            await _run_input(partial(inj.key_down, key))
    elif t == "keyup":
        key = str(msg.get("key") or "")
        if key:
            await _run_input(partial(inj.key_up, key))


def _auth_token_from_start(start_msg: dict[str, Any], query_token: str | None) -> str | None:
    token = start_msg.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    if query_token and query_token.strip():
        return query_token.strip()
    return None


@router.websocket("/desktop-stream/ws")
async def desktop_stream_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    server = websocket.app.state.octop_server
    locale = resolve_request_locale(websocket)
    status = desktop_status(locale=locale)
    if status.setup_state != "ready" or not status.ok:
        await websocket.close(code=4003, reason=status.reason or status.setup_state)
        return

    await websocket.accept()
    user: User | None = None
    session: DesktopSession | None = None
    stream_task: asyncio.Task[None] | None = None
    frame_dims = [0, 0]
    user_id = ""
    replaced = False

    async def _force_disconnect() -> None:
        nonlocal stream_task, replaced
        replaced = True
        if stream_task is not None and not stream_task.done():
            stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stream_task
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close(code=4000, reason="replaced by new connection")

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
            user = resolve_user_from_token(server, auth_token)
        except Exception as exc:
            await _send_json(
                websocket, {"type": "error", "code": "AUTH_FAILED", "message": str(exc)}
            )
            await websocket.close(code=4001, reason=f"auth failed: {exc}")
            return
        if not user.is_admin:
            await websocket.close(code=4003, reason="admin required")
            return

        user_id = str(user.id)
        monitor = int(start_msg.get("monitor") or 0)
        quality, max_fps = _clamp_stream_params(
            int(start_msg.get("quality") or 80),
            float(start_msg.get("max_fps") or _DEFAULT_FPS),
        )
        display = _resolve_display()

        try:
            session = await acquire_session(
                user_id=user_id,
                display=display,
                monitor=monitor,
            )
        except DesktopSessionLimitError as exc:
            err = OctopError.localized(
                ErrorCode.DESKTOP_SESSION_LIMIT,
                locale,
                details={"limit": exc.limit},
            )
            await _send_json(
                websocket,
                {
                    "type": "error",
                    "code": err.code.value,
                    "message": err.message,
                    "details": err.details,
                },
            )
            await websocket.close(code=4029, reason=err.code.value)
            return

        await supersede_user_stream(user_id, _force_disconnect)

        stream_task = asyncio.create_task(
            _stream_loop(
                websocket,
                session,
                quality=quality,
                max_fps=max_fps,
                frame_dims=frame_dims,
                locale=locale,
            )
        )

        while websocket.application_state == WebSocketState.CONNECTED:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "stop":
                break
            if session is not None:
                try:
                    await _handle_input(
                        websocket,
                        session,
                        msg,
                        frame_width=frame_dims[0],
                        frame_height=frame_dims[1],
                    )
                except Exception:
                    logger.exception("desktop input failed")
    except TimeoutError:
        await _send_json(websocket, {"type": "error", "message": "timed out waiting for start"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("desktop stream failed")
        if websocket.application_state == WebSocketState.CONNECTED:
            await _send_json(websocket, {"type": "error", "message": str(exc)})
            await _send_json(websocket, {"type": "status", "status": "error"})
    finally:
        if user_id:
            await clear_user_stream(user_id, _force_disconnect)
        if stream_task is not None and not stream_task.done():
            stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stream_task
        if session is not None and user_id and not replaced:
            await release_session(user_id=user_id, session=session)
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()
