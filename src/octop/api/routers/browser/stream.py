"""WebSocket browser screencast — attaches to harness-browser sessions.

Wire protocol matches the dashboard ``useBrowserStream`` hook (screencast)
and ``useBrowserSessionState`` (listen-only status):

Client → Server::

  {"type": "start", "url": "", "width": 1280, "height": 800,
   "reuse_session": true, "session_id": "<profile>"}
  {"type": "navigate", "url": "https://..."}
  {"type": "click", "x": 100, "y": 200}
  {"type": "mousedown", "x": 100, "y": 200, "button": "left", "buttons": 1}
  {"type": "mousemove", "x": 150, "y": 250, "button": "left", "buttons": 1}
  {"type": "mousemove", "x": 160, "y": 260, "button": "none", "buttons": 0}
  {"type": "mouseup", "x": 150, "y": 250, "button": "left", "buttons": 0}
  {"type": "stop"}

Server → Client::

  {"type": "status", "status": "streaming"}
  {"type": "frame", "data": "<base64 jpeg>"}
  {"type": "tabs", "tabs": [{id, url, title, active}]}
  {"type": "session_update", "session_id": "...", "current_url": "...", ...}
  {"type": "error", "message": "..."}

Auth: ``?token=<JWT>`` query param (browsers cannot set Authorization on WS).
Listen-only (``?listen_only=1``): still requires ``start``, but never launches
Chrome — attaches to an existing harness session or pushes idle updates.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
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
from octop.infra.utils.browser_media import user_browser_profile

logger = logging.getLogger(__name__)

router = APIRouter()

_FRAME_INTERVAL_S = 1 / 12
_SESSION_INTERVAL_S = 1.0


def _normalize_nav_url(raw: str) -> str:
    """Prefix a host with ``https://`` unless it already has an http(s) scheme.

    Matches :func:`octop.infra.utils.url.normalize_nav_url`, including the
    case-insensitive scheme check: ``HTTPS://host`` must not become
    ``https://HTTPS://host``.
    """
    t = raw.strip()
    if not t:
        return ""
    if t.lower().startswith(("http://", "https://")):
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


async def _send_session_snapshot(
    ws: WebSocket,
    profile: str,
    *,
    sess: Any | None,
) -> None:
    """Push one session_update (+ tabs) frame for *profile*."""
    if sess is None:
        await _send_json(
            ws,
            {
                "type": "session_update",
                "session_id": profile,
                "conversation_id": profile,
                "channel_source": "dashboard",
                "state": "idle",
                "control_owner": control_owner_for(profile),
                "current_url": "",
            },
        )
        await _send_json(ws, {"type": "tabs", "tabs": []})
        return

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


async def _stream_loop(
    ws: WebSocket,
    sess: Any,
    profile: str,
    *,
    listen_only: bool,
) -> None:
    await _send_json(ws, {"type": "status", "status": "browser_started"})
    await _send_json(ws, {"type": "status", "status": "streaming"})

    next_snapshot = 0.0
    while ws.application_state == WebSocketState.CONNECTED:
        started = time.monotonic()
        if started >= next_snapshot:
            await _send_session_snapshot(ws, profile, sess=sess)
            next_snapshot = started + _SESSION_INTERVAL_S

        if not listen_only:
            frame = await _capture_jpeg(sess)
            if frame:
                await _send_json(ws, {"type": "frame", "data": frame})

        await asyncio.sleep(max(0, _FRAME_INTERVAL_S - (time.monotonic() - started)))


async def _listen_state_loop(ws: WebSocket, profile: str) -> None:
    """Push session_update events without launching Chrome or capturing frames.

    Re-resolves the harness registry each tick so a browser started later by
    the agent becomes visible without reconnecting. Idle (no session) ticks
    use a longer interval to avoid a request/render storm on the dashboard.
    """
    await _send_json(ws, {"type": "status", "status": "streaming"})

    while ws.application_state == WebSocketState.CONNECTED:
        sess = await resolve_harness_session(profile, create=False)
        await _send_session_snapshot(ws, profile, sess=sess)
        await asyncio.sleep(_SESSION_INTERVAL_S if sess is not None else 2.0)


_CDP_BUTTON_MASK = {"left": 1, "right": 2, "middle": 4, "none": 0}


def _cdp_button(raw: object) -> str:
    name = str(raw or "left").lower()
    return name if name in _CDP_BUTTON_MASK else "left"


def _cdp_buttons(msg: dict[str, Any], *, button: str, event: str) -> int:
    if "buttons" in msg and msg["buttons"] is not None:
        try:
            return max(0, int(msg["buttons"]))
        except (TypeError, ValueError):
            pass
    if event == "mouseup" or button == "none":
        return 0
    return _CDP_BUTTON_MASK.get(button, 0)


async def _dispatch_mouse(
    sess: Any,
    *,
    event_type: str,
    x: int,
    y: int,
    button: str = "none",
    buttons: int = 0,
    click_count: int = 0,
) -> None:
    params: dict[str, Any] = {
        "type": event_type,
        "x": x,
        "y": y,
        "button": button,
        "buttons": buttons,
    }
    if click_count:
        params["clickCount"] = click_count
    await sess._internal.client.send("Input.dispatchMouseEvent", params)  # noqa: SLF001


def _cdp_click_count(msg: dict[str, Any]) -> int:
    raw = msg.get("clickCount", msg.get("click_count", 1))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


_KEY_CODES = {
    "Backspace": 8,
    "Tab": 9,
    "Enter": 13,
    "Escape": 27,
    "PageUp": 33,
    "PageDown": 34,
    "End": 35,
    "Home": 36,
    "ArrowLeft": 37,
    "ArrowUp": 38,
    "ArrowRight": 39,
    "ArrowDown": 40,
    "Delete": 46,
}


async def _dispatch_key(sess: Any, msg: dict[str, Any]) -> None:
    key = str(msg.get("key") or "")
    if not key or key in {"Process", "Dead", "Unidentified"}:
        return
    modifiers = sum(
        bit
        for field, bit in (("altKey", 1), ("ctrlKey", 2), ("metaKey", 4), ("shiftKey", 8))
        if msg.get(field)
    )
    key_code = _KEY_CODES.get(key, ord(key.upper()) if len(key) == 1 and key.isascii() else 0)
    params: dict[str, Any] = {
        "key": key,
        "code": str(msg.get("code") or key),
        "windowsVirtualKeyCode": int(msg.get("keyCode") or key_code),
        "modifiers": modifiers,
    }
    down = {**params, "type": "rawKeyDown", "autoRepeat": bool(msg.get("repeat"))}
    if key == "Enter":
        down.update(type="keyDown", text="\r", unmodifiedText="\r")
    if key.lower() == "a" and modifiers & 6 and not modifiers & 1:
        # Chromium's native editing shortcuts depend on the server OS. Keep
        # Ctrl+A / Cmd+A working when the dashboard and Chrome run on different OSes.
        down["commands"] = ["selectAll"]
    await sess._internal.client.send("Input.dispatchKeyEvent", down)  # noqa: SLF001
    await sess._internal.client.send(  # noqa: SLF001
        "Input.dispatchKeyEvent", {**params, "type": "keyUp"}
    )


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
    elif t in ("mousedown", "mouseup", "mousemove"):
        x, y = int(msg.get("x") or 0), int(msg.get("y") or 0)
        button = _cdp_button(msg.get("button"))
        buttons = _cdp_buttons(msg, button=button, event=str(t))
        click_count = _cdp_click_count(msg)
        if t == "mousedown":
            await _dispatch_mouse(
                sess,
                event_type="mousePressed",
                x=x,
                y=y,
                button=button if button != "none" else "left",
                buttons=buttons or _CDP_BUTTON_MASK.get(button, 1),
                click_count=click_count,
            )
        elif t == "mouseup":
            await _dispatch_mouse(
                sess,
                event_type="mouseReleased",
                x=x,
                y=y,
                button=button if button != "none" else "left",
                buttons=0,
                click_count=click_count,
            )
        else:
            await _dispatch_mouse(
                sess,
                event_type="mouseMoved",
                x=x,
                y=y,
                button=button,
                buttons=buttons,
            )
    elif t == "scroll":
        delta_x = float(msg.get("deltaX") or msg.get("delta_x") or 0)
        delta_y = float(msg.get("deltaY") or msg.get("delta_y") or 0)
        x = int(msg.get("x") or 0)
        y = int(msg.get("y") or 0)
        if abs(delta_x) > 0.5 or abs(delta_y) > 0.5:
            with contextlib.suppress(Exception):
                await _dispatch_mouse(sess, event_type="mouseMoved", x=x, y=y)
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
            # Committed IME / pasted text is one insertion, not one CDP round
            # trip per character. The page's input event still reaches the recorder.
            await sess._internal.client.send("Input.insertText", {"text": text})  # noqa: SLF001
    elif t == "keydown":
        await _dispatch_key(sess, msg)
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
        user = resolve_user_from_token(server, token)
    except Exception as exc:
        await websocket.close(code=4001, reason=f"auth failed: {exc}")
        return

    await websocket.accept()
    sess: Any | None = None
    profile = user_browser_profile(user.id)
    stream_task: asyncio.Task[None] | None = None
    listen = bool(listen_only)

    try:
        # Wait for the client's ``start`` message (sent on ws.onopen).
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
        start_msg = json.loads(raw)
        if start_msg.get("type") != "start":
            await _send_json(websocket, {"type": "error", "message": "expected start message"})
            return

        if listen:
            # Status-only clients (chat browser badge) must not spawn Chrome.
            stream_task = asyncio.create_task(_listen_state_loop(websocket, profile))
        else:
            sess = await resolve_harness_session(profile)
            assert sess is not None  # create=True always returns or raises

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
                _stream_loop(websocket, sess, profile, listen_only=False)
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
