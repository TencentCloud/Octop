"""WebSocket Remote Android stream — H.264 screenrecord with JPEG fallback."""

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
from octop.infra.mobile.adb import (
    KEYCODE_APP_SWITCH,
    KEYCODE_BACK,
    KEYCODE_HOME,
    KEYCODE_POWER,
    KEYCODE_VOLUME_DOWN,
    KEYCODE_VOLUME_UP,
    capture_jpeg_frame,
    find_adb,
    input_text,
    keyevent,
    list_devices,
    screenrecord_h264_args,
    swipe,
    tap,
    wm_size,
)
from octop.infra.mobile.agent_control import (
    clear_mobile_agent_control_if_device,
    set_mobile_agent_control,
)
from octop.infra.mobile.h264 import (
    NAL_IDR,
    NAL_PPS,
    NAL_SLICE,
    NAL_SPS,
    AnnexBSplitter,
    avc_codec_string,
    avcc_from_sps_pps,
    avcc_sample,
    nal_type,
)
from octop.infra.mobile.setup import mobile_status
from octop.infra.users.identity import User
from octop.infra.users.permissions import user_has_permission
from octop.infra.utils.locale import resolve_request_locale

logger = logging.getLogger(__name__)

router = APIRouter()

_DEFAULT_FPS = 10.0
_MIN_QUALITY = 30
_MAX_QUALITY = 95
_MIN_FPS = 1.0
_MAX_FPS = 20.0
_CAPTURE_TIMEOUT_S = 8.0
_INPUT_TIMEOUT_S = 25.0
_START_TIMEOUT_S = 15.0
_H264_PROBE_S = 2.0
_H264_FIRST_FRAME_S = 3.0
_H264_BIT_RATE = 2_500_000
_H264_SIZE = "720x1600"
_JPEG_MAX_SIDE_DEFAULT = 1080
_JPEG_MAX_SIDE_CAP = 2160
_SWIPE_THRESHOLD_PX = 28
_KEY_ALIASES: dict[str, int] = {
    "back": KEYCODE_BACK,
    "home": KEYCODE_HOME,
    "recents": KEYCODE_APP_SWITCH,
    "app_switch": KEYCODE_APP_SWITCH,
    "power": KEYCODE_POWER,
    "volume_up": KEYCODE_VOLUME_UP,
    "volume_down": KEYCODE_VOLUME_DOWN,
}
# Browser KeyboardEvent.key → Android keycode (adb input keyevent).
_BROWSER_KEY_TO_ANDROID: dict[str, int] = {
    "Enter": 66,
    "Backspace": 67,
    "Delete": 112,
    "Tab": 61,
    "Escape": 111,
    "ArrowUp": 19,
    "ArrowDown": 20,
    "ArrowLeft": 21,
    "ArrowRight": 22,
    "Home": 3,
    "End": 123,
    "PageUp": 92,
    "PageDown": 93,
    " ": 62,
}


def _clamp_stream_params(quality: int, max_fps: float, max_side: int) -> tuple[int, float, int]:
    q = max(_MIN_QUALITY, min(_MAX_QUALITY, quality))
    fps = max(_MIN_FPS, min(_MAX_FPS, max_fps))
    # 0 = native resolution (no downscale).
    side = 0 if max_side <= 0 else max(480, min(_JPEG_MAX_SIDE_CAP, max_side))
    return q, fps, side


async def _send_json(ws: WebSocket, payload: dict[str, Any]) -> None:
    if ws.application_state == WebSocketState.CONNECTED:
        await ws.send_text(json.dumps(payload))


async def _send_bytes(ws: WebSocket, payload: bytes) -> None:
    if ws.application_state == WebSocketState.CONNECTED:
        await ws.send_bytes(payload)


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
    max_side: int,
    frame_dims: list[int],
) -> None:
    interval = 1.0 / max_fps
    adb = find_adb()
    while ws.application_state == WebSocketState.CONNECTED:
        loop = asyncio.get_running_loop()
        t0 = asyncio.get_running_loop().time()
        try:
            captured = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    partial(
                        capture_jpeg_frame,
                        device,
                        quality=quality,
                        max_side=max_side,
                        adb=adb,
                    ),
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
        jpeg, _stream_w, _stream_h, device_w, device_h = captured
        # Tap/swipe mapping must use the real device resolution, not the
        # downscaled JPEG bitmap the canvas displays.
        frame_dims[0] = device_w
        frame_dims[1] = device_h
        await _send_json(
            ws,
            {
                "type": "frame",
                "data": base64.b64encode(jpeg).decode("ascii"),
                "width": _stream_w,
                "height": _stream_h,
            },
        )
        elapsed = asyncio.get_running_loop().time() - t0
        await asyncio.sleep(max(0.0, interval - elapsed))


async def _stream_h264(
    ws: WebSocket,
    *,
    device: str,
    frame_dims: list[int],
    first_frame: asyncio.Event,
) -> None:
    adb = find_adb()
    if not adb:
        return
    # Prefer primary display size for coords; skip --display-id (can stall on emulator).
    size = await asyncio.to_thread(wm_size, device, adb=adb)
    args = screenrecord_h264_args(
        device,
        adb=adb,
        display_id=None,
        bit_rate=_H264_BIT_RATE,
        size=_H264_SIZE,
    )
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    splitter = AnnexBSplitter()
    sps: bytes | None = None
    pps: bytes | None = None
    init_sent = False
    try:
        stdout = proc.stdout
        if stdout is None:
            return
        while ws.application_state == WebSocketState.CONNECTED:
            data = await stdout.read(65536)
            if not data:
                break
            for nal in splitter.feed(data):
                kind = nal_type(nal)
                if kind == NAL_SPS:
                    sps = nal
                    continue
                if kind == NAL_PPS:
                    pps = nal
                    continue
                if kind not in {NAL_SLICE, NAL_IDR}:
                    continue
                if not (sps and pps):
                    continue
                if not init_sent:
                    width, height = size or (0, 0)
                    if width > 0 and height > 0:
                        frame_dims[0] = width
                        frame_dims[1] = height
                    await _send_json(
                        ws,
                        {
                            "type": "video_init",
                            "codec": avc_codec_string(sps),
                            "description": base64.b64encode(avcc_from_sps_pps(sps, pps)).decode(
                                "ascii"
                            ),
                            "width": width,
                            "height": height,
                        },
                    )
                    init_sent = True
                flag = 1 if kind == NAL_IDR else 0
                await _send_bytes(ws, bytes([flag]) + avcc_sample([nal]))
                if not first_frame.is_set():
                    first_frame.set()
    finally:
        if proc.returncode is None:
            proc.kill()
            with contextlib.suppress(ProcessLookupError, TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=2)


def _msg_device_point(
    msg: dict[str, Any],
    *,
    frame_dims: list[int],
    x_key: str = "x",
    y_key: str = "y",
) -> tuple[int, int]:
    fw, fh = frame_dims[0], frame_dims[1]
    return _canvas_to_device(
        float(msg.get(x_key) or 0),
        float(msg.get(y_key) or 0),
        canvas_width=int(msg.get("canvas_width") or fw),
        canvas_height=int(msg.get("canvas_height") or fh),
        frame_width=fw,
        frame_height=fh,
    )


async def _run_adb_action(
    ws: WebSocket,
    *,
    action: str,
    fn: Any,
) -> None:
    loop = asyncio.get_running_loop()
    try:
        ok = await asyncio.wait_for(
            loop.run_in_executor(None, fn),
            timeout=_INPUT_TIMEOUT_S,
        )
    except TimeoutError:
        ok = False
    await _send_json(ws, {"type": "action_result", "action": action, "ok": bool(ok)})


async def _handle_input(
    ws: WebSocket,
    msg: dict[str, Any],
    *,
    device: str,
    frame_dims: list[int],
    press: dict[str, int | None],
) -> None:
    """Map dashboard pointer events to adb tap/swipe/keyevent.

    The shared canvas hook emits browser-style ``mousedown`` / ``mouseup`` /
    ``mousemove``. Pure click → tap; drag past threshold → swipe.

    ADB calls are scheduled in the background so a slow ``input tap`` cannot
    stall the WebSocket receive loop (or queue behind the next click).
    """
    t = msg.get("type")
    adb = find_adb()

    if t == "mousedown":
        if str(msg.get("button") or "left") != "left":
            return
        x, y = _msg_device_point(msg, frame_dims=frame_dims)
        press["x"] = x
        press["y"] = y
        return

    if t == "mousemove":
        return

    if t in {"click", "mouseup"}:
        x, y = _msg_device_point(msg, frame_dims=frame_dims)
        x0, y0 = press.get("x"), press.get("y")
        press["x"] = None
        press["y"] = None
        if (
            x0 is not None
            and y0 is not None
            and (abs(x - x0) >= _SWIPE_THRESHOLD_PX or abs(y - y0) >= _SWIPE_THRESHOLD_PX)
        ):
            asyncio.create_task(
                _run_adb_action(
                    ws,
                    action="swipe",
                    fn=partial(swipe, device, int(x0), int(y0), x, y, adb=adb),
                )
            )
        else:
            # Prefer press point for taps — release can jitter a few pixels.
            tx = int(x0) if x0 is not None else x
            ty = int(y0) if y0 is not None else y
            asyncio.create_task(
                _run_adb_action(
                    ws,
                    action="click",
                    fn=partial(tap, device, tx, ty, adb=adb),
                )
            )
        return

    if t == "swipe":
        x1, y1 = _msg_device_point(msg, frame_dims=frame_dims, x_key="x1", y_key="y1")
        x2, y2 = _msg_device_point(msg, frame_dims=frame_dims, x_key="x2", y_key="y2")
        asyncio.create_task(
            _run_adb_action(
                ws,
                action="swipe",
                fn=partial(swipe, device, x1, y1, x2, y2, adb=adb),
            )
        )
        return

    if t == "type":
        text = str(msg.get("text") or "")
        if not text:
            return
        asyncio.create_task(
            _run_adb_action(
                ws,
                action="type",
                fn=partial(input_text, device, text, adb=adb),
            )
        )
        return

    if t == "keydown":
        key = str(msg.get("key") or "")
        code = _BROWSER_KEY_TO_ANDROID.get(key)
        if code is None:
            return
        asyncio.create_task(
            _run_adb_action(
                ws,
                action="keyevent",
                fn=partial(keyevent, device, code, adb=adb),
            )
        )
        return

    if t == "keyup":
        return

    if t == "keyevent":
        raw_key = msg.get("key") if msg.get("key") is not None else msg.get("keycode")
        keycode: int | None = None
        if isinstance(raw_key, int):
            keycode = raw_key
        elif isinstance(raw_key, str):
            alias = raw_key.strip().lower()
            if alias in _KEY_ALIASES:
                keycode = _KEY_ALIASES[alias]
            elif alias.isdigit():
                keycode = int(alias)
        if keycode is None:
            await _send_json(
                ws,
                {
                    "type": "action_result",
                    "action": "keyevent",
                    "ok": False,
                    "message": "unknown key",
                },
            )
            return
        asyncio.create_task(
            _run_adb_action(
                ws,
                action="keyevent",
                fn=partial(keyevent, device, keycode, adb=adb),
            )
        )


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
    bound_device: str | None = None

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

        # Connecting the phone stream binds it for agent tools (same idea as
        # an active browser / desktop session) — no separate UI toggle.
        set_mobile_agent_control(enabled=True, device=device)
        bound_device = device

        quality, max_fps, max_side = _clamp_stream_params(
            int(start_msg.get("quality") or 80),
            float(start_msg.get("max_fps") or _DEFAULT_FPS),
            int(
                start_msg.get("max_side")
                if start_msg.get("max_side") is not None
                else _JPEG_MAX_SIDE_DEFAULT
            ),
        )
        prefer = str(start_msg.get("codec") or "jpeg").lower()

        if prefer != "jpeg":
            first_frame = asyncio.Event()
            h264_task = asyncio.create_task(
                _stream_h264(
                    websocket,
                    device=device,
                    frame_dims=frame_dims,
                    first_frame=first_frame,
                )
            )
            use_h264 = False
            try:
                await asyncio.wait_for(
                    first_frame.wait(),
                    timeout=_H264_PROBE_S + _H264_FIRST_FRAME_S,
                )
                use_h264 = True
            except TimeoutError:
                use_h264 = False
            if use_h264:
                stream_task = h264_task
            else:
                h264_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await h264_task
                logger.info(
                    "mobile H.264 unavailable/stalled; falling back to JPEG (device=%s)",
                    device,
                )
                stream_task = asyncio.create_task(
                    _stream_frames(
                        websocket,
                        device=device,
                        quality=quality,
                        max_fps=max_fps,
                        max_side=max_side,
                        frame_dims=frame_dims,
                    )
                )
        else:
            stream_task = asyncio.create_task(
                _stream_frames(
                    websocket,
                    device=device,
                    quality=quality,
                    max_fps=max_fps,
                    max_side=max_side,
                    frame_dims=frame_dims,
                )
            )

        press: dict[str, int | None] = {"x": None, "y": None}
        while True:
            msg_raw = await websocket.receive_text()
            msg = json.loads(msg_raw)
            if msg.get("type") == "stop":
                break
            try:
                await _handle_input(
                    websocket,
                    msg,
                    device=device,
                    frame_dims=frame_dims,
                    press=press,
                )
            except Exception:
                logger.exception("mobile input failed (device=%s)", device)
    except WebSocketDisconnect:
        pass
    except TimeoutError:
        # Only the start handshake uses wait_for at this level.
        with contextlib.suppress(Exception):
            await websocket.close(code=4008, reason="start timeout")
    except Exception:
        logger.exception("mobile stream failed")
    finally:
        if bound_device is not None:
            clear_mobile_agent_control_if_device(bound_device)
        if stream_task is not None and not stream_task.done():
            stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stream_task
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()
