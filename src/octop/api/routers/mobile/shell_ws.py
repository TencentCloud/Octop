"""WebSocket PTY for ``adb -s <serial> shell``."""

from __future__ import annotations

import asyncio
import contextlib
import errno
import json
import logging
import os
import signal
import subprocess
from functools import partial
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from octop.api.deps import resolve_user_from_token
from octop.infra.mobile.adb import find_adb, list_devices
from octop.infra.users.identity import User
from octop.infra.users.permissions import user_has_permission
from octop.infra.utils import posix_compat

logger = logging.getLogger(__name__)

router = APIRouter()


def _set_winsize(fd: int, cols: int, rows: int) -> None:
    posix_compat.set_winsize(fd, cols, rows)


def _read_nonblock(fd: int) -> bytes | None:
    try:
        return os.read(fd, 4096)
    except OSError as exc:
        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
            return None
        return b""


def _write_pty(fd: int, data: bytes) -> None:
    os.write(fd, data)


async def _send_json(ws: WebSocket, payload: dict[str, Any]) -> None:
    if ws.application_state == WebSocketState.CONNECTED:
        await ws.send_text(json.dumps(payload))


@router.websocket("/mobile/adb/shell/ws")
async def adb_shell_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    serial: str | None = Query(default=None),
    cols: int = Query(default=120, ge=20, le=500),
    rows: int = Query(default=32, ge=5, le=200),
) -> None:
    server = websocket.app.state.octop_server
    adb = find_adb()
    if not adb or os.name != "posix":
        await websocket.close(code=4003, reason="adb shell unavailable")
        return

    await websocket.accept()

    if not token or not token.strip():
        await _send_json(websocket, {"type": "error", "message": "missing token"})
        await websocket.close(code=4001, reason="missing token")
        return
    try:
        user: User = resolve_user_from_token(server, token.strip())
    except Exception as exc:
        await _send_json(websocket, {"type": "error", "message": f"auth failed: {exc}"})
        await websocket.close(code=4001, reason=f"auth failed: {exc}")
        return
    if not user_has_permission(user, "mobile"):
        await _send_json(websocket, {"type": "error", "message": "permission required"})
        await websocket.close(code=4003, reason="permission required")
        return

    device = (serial or "").strip()
    connected = await asyncio.to_thread(list_devices)
    if not device or device not in connected:
        await _send_json(websocket, {"type": "error", "message": "device unavailable"})
        await websocket.close(code=4003, reason="device unavailable")
        return

    master_fd, slave_fd = posix_compat.openpty()
    _set_winsize(master_fd, cols, rows)
    posix_compat.set_nonblock(master_fd)

    try:
        proc = subprocess.Popen(
            [adb, "-s", device, "shell"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        os.close(master_fd)
        with contextlib.suppress(OSError):
            os.close(slave_fd)
        await _send_json(websocket, {"type": "error", "message": str(exc)})
        await websocket.close(code=1011, reason="spawn failed")
        return
    finally:
        with contextlib.suppress(OSError):
            os.close(slave_fd)

    loop = asyncio.get_running_loop()
    closed = asyncio.Event()

    async def pump_output() -> None:
        while not closed.is_set():
            chunk = await loop.run_in_executor(None, _read_nonblock, master_fd)
            if chunk is None:
                if proc.poll() is not None:
                    break
                await asyncio.sleep(0.02)
                continue
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            await _send_json(websocket, {"type": "output", "data": text})

    pump_task = asyncio.create_task(pump_output())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            t = msg.get("type")
            if t == "input":
                data = msg.get("data")
                if isinstance(data, str) and data:
                    await loop.run_in_executor(
                        None,
                        _write_pty,
                        master_fd,
                        data.encode("utf-8", errors="replace"),
                    )
            elif t == "resize":
                c = int(msg.get("cols") or cols)
                r = int(msg.get("rows") or rows)
                await loop.run_in_executor(None, _set_winsize, master_fd, c, r)
    except WebSocketDisconnect:
        pass
    finally:
        closed.set()
        pump_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump_task
        with contextlib.suppress(OSError):
            os.close(master_fd)
        if proc.poll() is None:
            with contextlib.suppress(OSError, ProcessLookupError):
                posix_compat.killpg(posix_compat.getpgid(proc.pid), signal.SIGTERM)
            with contextlib.suppress(subprocess.TimeoutExpired):
                await loop.run_in_executor(None, partial(proc.wait, timeout=1))
        code = proc.poll()
        if code is not None:
            await _send_json(websocket, {"type": "exit", "code": code})
