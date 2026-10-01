"""``resize`` frames on the adb-shell WebSocket are validated instead of fatal (issue #1475).

These drive the handler directly with the PTY, subprocess and auth layers stubbed, so they run on
Windows too -- the route itself refuses non-POSIX, which is exactly why no live capture of the
1011 was possible. The ``set_winsize`` stub contains the same ``struct.pack("HHHH", rows, cols, 0, 0)``
statement that ``posix_compat.set_winsize`` runs on a real host, so an unvalidated size fails here the
way it fails in production.
"""

from __future__ import annotations

import json
import struct
import subprocess
from types import SimpleNamespace

from starlette.websockets import WebSocketDisconnect, WebSocketState

from octop.api.routers.mobile import shell_ws

DEVICE = "emulator-5554"
MASTER_FD = 41


class _FakeWS:
    """Minimal stand-in for the handler's WebSocket argument."""

    def __init__(self, received: tuple[str, ...]) -> None:
        self.app = SimpleNamespace(state=SimpleNamespace(octop_server=object()))
        self.application_state = WebSocketState.CONNECTING
        self._received = list(received)
        self.sent: list[str] = []
        self.close_code: int | None = None

    async def accept(self) -> None:
        self.application_state = WebSocketState.CONNECTED

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def receive_text(self) -> str:
        if not self._received:
            raise WebSocketDisconnect()
        return self._received.pop(0)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.close_code = code
        self.application_state = WebSocketState.DISCONNECTED


def _resize(**dims: object) -> str:
    return json.dumps({"type": "resize", **dims})


def _install(monkeypatch, received: tuple[str, ...]) -> tuple[_FakeWS, list[tuple[int, int, int]]]:
    """Patch every host layer the handler touches and return (ws, sizes applied to the PTY)."""
    applied: list[tuple[int, int, int]] = []

    def set_winsize(fd: int, cols: int, rows: int) -> None:
        struct.pack("HHHH", rows, cols, 0, 0)
        applied.append((fd, cols, rows))

    proc = SimpleNamespace(pid=4321, poll=lambda: None, wait=lambda timeout: None)

    monkeypatch.setattr(shell_ws, "find_adb", lambda: "/usr/bin/adb")
    monkeypatch.setattr(shell_ws, "list_devices", lambda: [DEVICE])
    monkeypatch.setattr(shell_ws, "resolve_user_from_token", lambda _s, _t: SimpleNamespace(id=1))
    monkeypatch.setattr(shell_ws, "user_has_permission", lambda _u, _p: True)
    monkeypatch.setattr(
        shell_ws,
        "os",
        SimpleNamespace(
            name="posix",
            read=lambda _fd, _size: b"",
            write=lambda _fd, _data: None,
            close=lambda _fd: None,
        ),
    )
    monkeypatch.setattr(shell_ws.posix_compat, "openpty", lambda: (MASTER_FD, 42))
    monkeypatch.setattr(shell_ws.posix_compat, "set_nonblock", lambda _fd: None)
    monkeypatch.setattr(shell_ws.posix_compat, "set_winsize", set_winsize)
    monkeypatch.setattr(shell_ws.posix_compat, "getpgid", lambda _pid: 7)
    monkeypatch.setattr(shell_ws.posix_compat, "killpg", lambda _pgid, _sig: None)
    monkeypatch.setattr(
        shell_ws,
        "subprocess",
        SimpleNamespace(
            Popen=lambda *args, **kwargs: proc, TimeoutExpired=subprocess.TimeoutExpired
        ),
    )
    return _FakeWS(received), applied


async def _run(
    monkeypatch,
    received: tuple[str, ...],
    *,
    cols: int = 120,
    rows: int = 32,
) -> tuple[_FakeWS, list[tuple[int, int, int]]]:
    ws, applied = _install(monkeypatch, received)
    await shell_ws.adb_shell_ws(ws, token="t", serial=DEVICE, cols=cols, rows=rows)
    return ws, applied


async def test_handshake_size_is_applied_without_any_frame(monkeypatch) -> None:
    _ws, applied = await _run(monkeypatch, ())

    assert applied == [(MASTER_FD, 120, 32)]


async def test_valid_resize_frame_is_applied(monkeypatch) -> None:
    ws, applied = await _run(monkeypatch, (_resize(cols=100, rows=40),))

    assert applied == [(MASTER_FD, 120, 32), (MASTER_FD, 100, 40)]
    assert ws.close_code is None


async def test_resize_without_dimensions_falls_back_to_the_handshake_size(monkeypatch) -> None:
    _ws, applied = await _run(monkeypatch, (_resize(),))

    assert applied == [(MASTER_FD, 120, 32), (MASTER_FD, 120, 32)]


async def test_endpoints_of_the_handshake_range_are_still_accepted(monkeypatch) -> None:
    frames = (
        _resize(cols=20, rows=5),
        _resize(cols=500, rows=200),
    )

    _ws, applied = await _run(monkeypatch, frames)

    assert applied == [
        (MASTER_FD, 120, 32),
        (MASTER_FD, 20, 5),
        (MASTER_FD, 500, 200),
    ]


async def test_oversized_cols_is_ignored_and_the_session_survives(monkeypatch) -> None:
    frames = (
        _resize(cols=70000, rows=32),
        _resize(cols=90, rows=36),
    )

    ws, applied = await _run(monkeypatch, frames)

    assert applied == [(MASTER_FD, 120, 32), (MASTER_FD, 90, 36)]
    assert ws.close_code is None


async def test_negative_cols_is_ignored_and_the_previous_size_is_kept(monkeypatch) -> None:
    frames = (
        _resize(cols=100, rows=40),
        _resize(cols=-1, rows=32),
    )

    ws, applied = await _run(monkeypatch, frames)

    assert applied == [(MASTER_FD, 120, 32), (MASTER_FD, 100, 40)]
    assert ws.close_code is None


async def test_out_of_range_rows_is_ignored(monkeypatch) -> None:
    frames = (
        _resize(cols=100, rows=1),
        _resize(cols=100, rows=9999),
        _resize(cols=80, rows=24),
    )

    _ws, applied = await _run(monkeypatch, frames)

    assert applied == [(MASTER_FD, 120, 32), (MASTER_FD, 80, 24)]


async def test_string_cols_is_ignored(monkeypatch) -> None:
    frames = (
        _resize(cols="abc", rows=32),
        _resize(cols=80, rows=24),
    )

    _ws, applied = await _run(monkeypatch, frames)

    assert applied == [(MASTER_FD, 120, 32), (MASTER_FD, 80, 24)]


async def test_array_cols_is_ignored(monkeypatch) -> None:
    frames = (
        _resize(cols=[1], rows=32),
        _resize(cols=80, rows=24),
    )

    _ws, applied = await _run(monkeypatch, frames)

    assert applied == [(MASTER_FD, 120, 32), (MASTER_FD, 80, 24)]


async def test_infinity_cols_is_ignored(monkeypatch) -> None:
    # ``json.dumps`` emits the non-standard ``Infinity`` literal that ``json.loads`` accepts here.
    assert "Infinity" in _resize(cols=float("inf"), rows=32)

    frames = (
        _resize(cols=float("inf"), rows=32),
        _resize(cols=80, rows=24),
    )

    _ws, applied = await _run(monkeypatch, frames)

    assert applied == [(MASTER_FD, 120, 32), (MASTER_FD, 80, 24)]


async def test_nan_cols_is_ignored(monkeypatch) -> None:
    # ``NaN`` is truthy, so ``msg.get("cols") or cols`` keeps it and ``int()`` raises.
    frames = (
        _resize(cols=float("nan"), rows=32),
        _resize(cols=80, rows=24),
    )

    _ws, applied = await _run(monkeypatch, frames)

    assert applied == [(MASTER_FD, 120, 32), (MASTER_FD, 80, 24)]
