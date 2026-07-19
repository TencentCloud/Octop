"""WebSocket browser screencast — attaches to harness-browser sessions.

Wire protocol matches the dashboard ``useBrowserStream`` hook:

Client → Server::

  {"type": "start", "url": "", "width": 1280, "height": 800,
   "reuse_session": true, "session_id": "<profile>"}
  {"type": "navigate", "url": "https://..."}
  {"type": "click", "x": 100, "y": 200}
  {"type": "stop"}

Server → Client::

  {"type": "status", "status": "streaming"}
  {"type": "frame", "data": "<base64 jpeg>"}
  {"type": "tabs", "tabs": [{id, url, title, active}]}
  {"type": "session_update", "session_id": "...", "current_url": "...", ...}
  {"type": "error", "message": "..."}

Auth: ``?token=<JWT>`` query param (browsers cannot set Authorization on WS).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from octop.api.deps import resolve_user_from_token
from octop.api.routers.browser.harness import (
    control_owner_for,
    harness_list_tabs,
    harness_page_url,
    resolve_harness_session,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_FRAME_INTERVAL_S = 0.25  # ~4 fps


def _normalize_nav_url(raw: str) -> str:
    t = raw.strip()
    if not t:
        return ""
    if t.startswith(("http://", "https://")):
        return t
    return f"https://{t}"


async def _capture_jpeg(sess: Any) -> str | None:
    try:
        # Check if internal session is fully connected to prevent race conditions during tab switching
        if not getattr(sess._internal, "_connected", False):  # noqa: SLF001
            return None

        # Wrap in a timeout to prevent hanging if the CDP client gets into an inconsistent state during reconnect
        result = await asyncio.wait_for(
            sess._internal.client.send(  # noqa: SLF001
                "Page.captureScreenshot",
                {"format": "jpeg", "quality": 80},
            ),
            timeout=1.5,
        )
        data = result.get("data")
        return str(data) if data else None
    except Exception as exc:
        logger.debug("capture jpeg failed: %s", exc)
        return None


async def _send_json(ws: WebSocket, payload: dict[str, Any]) -> None:
    if ws.application_state == WebSocketState.CONNECTED:
        await ws.send_text(json.dumps(payload))


async def _stream_loop(
    ws: WebSocket,
    sess: Any,
    profile: str,
    *,
    listen_only: bool,
) -> None:
    await _send_json(ws, {"type": "status", "status": "browser_started"})
    await _send_json(ws, {"type": "status", "status": "streaming"})

    while ws.application_state == WebSocketState.CONNECTED:
        url = await harness_page_url(sess)
        await _send_json(
            ws,
            {
                "type": "session_update",
                "session_id": profile,
                "conversation_id": profile,
                "channel_source": "dashboard",
                "state": "streaming" if url else "idle",
                "control_owner": control_owner_for(profile),
                "current_url": url,
            },
        )
        tabs = await harness_list_tabs(sess)
        await _send_json(ws, {"type": "tabs", "tabs": tabs})

        if not listen_only:
            frame = await _capture_jpeg(sess)
            if frame:
                await _send_json(ws, {"type": "frame", "data": frame})

        await asyncio.sleep(_FRAME_INTERVAL_S)


async def _handle_client_event(sess: Any, msg: dict[str, Any]) -> None:
    t = msg.get("type")
    if t == "navigate":
        url = _normalize_nav_url(str(msg.get("url") or ""))
        if url:
            await sess.navigate(url)
    elif t == "goback":
        await sess.go_back()
    elif t == "goforward":
        await sess.go_forward()
    elif t == "reload":
        await sess.reload()
    elif t == "click":
        await sess.click(x=int(msg.get("x") or 0), y=int(msg.get("y") or 0))
    elif t == "dblclick":
        x, y = int(msg.get("x") or 0), int(msg.get("y") or 0)
        await sess.click(x=x, y=y)
        await sess.click(x=x, y=y)
    elif t in ("mousedown", "mouseup"):
        pass  # click path covers typical UI; avoid duplicate CDP events
    elif t == "scroll":
        delta_x = float(msg.get("deltaX") or msg.get("delta_x") or 0)
        delta_y = float(msg.get("deltaY") or msg.get("delta_y") or 0)
        x = int(msg.get("x") or 0)
        y = int(msg.get("y") or 0)
        if abs(delta_x) > 0.5 or abs(delta_y) > 0.5:
            with contextlib.suppress(Exception):
                await sess._internal.client.send(  # noqa: SLF001
                    "Input.dispatchMouseEvent",
                    {"type": "mouseMoved", "x": x, "y": y},
                )
                await sess._internal.client.send(  # noqa: SLF001
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mouseWheel",
                        "x": x,
                        "y": y,
                        "deltaX": delta_x,
                        "deltaY": delta_y,
                    },
                )
        else:
            direction = "down" if delta_y > 0 else "up"
            amount = max(int(abs(delta_y)), 50)
            await sess.scroll(direction=direction, amount=amount)
    elif t == "type":
        text = str(msg.get("text") or "")
        if text:
            await sess.type(text)
    elif t == "keydown":
        key = str(msg.get("key") or "")
        if key in ("Enter",):
            await sess.type("\n")
    elif t == "tab_switch":
        tab_id = msg.get("tab_id")
        if tab_id is not None:
            await sess.switch_tab(str(tab_id))
    elif t == "tab_close":
        tab_id = msg.get("tab_id")
        if tab_id is not None:
            await sess.close_tab(str(tab_id))
    elif t == "tab_new":
        await sess.new_tab()
    elif t == "resize":
        w = int(msg.get("width") or 0)
        h = int(msg.get("height") or 0)
        if w > 0 and h > 0:
            with contextlib.suppress(Exception):
                await sess._internal.client.send(  # noqa: SLF001
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": w,
                        "height": h,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )


@router.websocket("/browser-stream/ws")
async def browser_stream_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    listen_only: int = Query(default=0),
    width: int = Query(default=1280),
    height: int = Query(default=800),
) -> None:
    server = websocket.app.state.octop_server
    if not token:
        await websocket.close(code=4001, reason="missing token")
        return
    try:
        resolve_user_from_token(server, token)
    except Exception as exc:
        await websocket.close(code=4001, reason=f"auth failed: {exc}")
        return

    await websocket.accept()
    sess: Any | None = None
    profile = "default"
    stream_task: asyncio.Task[None] | None = None
    listen = bool(listen_only)

    try:
        # Wait for the client's ``start`` message (sent on ws.onopen).
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
        start_msg = json.loads(raw)
        if start_msg.get("type") != "start":
            await _send_json(websocket, {"type": "error", "message": "expected start message"})
            return

        profile_hint = str(start_msg.get("session_id") or "auto")
        sess = await resolve_harness_session(profile_hint)
        profile = profile_hint if profile_hint not in {"", "auto"} else "default"

        start_url = _normalize_nav_url(str(start_msg.get("url") or ""))
        if start_url and start_url not in {"about:blank"}:
            try:
                await sess.navigate(start_url)
            except Exception as exc:
                # Don't let a bad/unreachable initial URL kill the whole
                # session — surface a warning and keep streaming so the
                # user can navigate manually.
                logger.warning("initial navigate to %s failed: %s", start_url, exc)
                await _send_json(
                    websocket,
                    {
                        "type": "error",
                        "message": f"导航到 {start_url} 失败：{exc}",
                    },
                )

        vw = int(start_msg.get("width") or width)
        vh = int(start_msg.get("height") or height)
        if vw > 0 and vh > 0:
            with contextlib.suppress(Exception):
                await sess._internal.client.send(  # noqa: SLF001
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": vw,
                        "height": vh,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )

        stream_task = asyncio.create_task(
            _stream_loop(websocket, sess, profile, listen_only=listen)
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
            if sess is not None:
                with contextlib.suppress(Exception):
                    await _handle_client_event(sess, msg)
    except TimeoutError:
        await _send_json(websocket, {"type": "error", "message": "timed out waiting for start"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("browser stream failed")
        if websocket.application_state == WebSocketState.CONNECTED:
            await _send_json(websocket, {"type": "error", "message": str(exc)})
            await _send_json(websocket, {"type": "status", "status": "error"})
    finally:
        if stream_task is not None:
            stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stream_task
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()
