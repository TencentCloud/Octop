"""Tests for the mobile stream route's client-frame loop.

Driven at unit level with a scripted WebSocket double: the route imports
cleanly on its own and every collaboration point (status probe, auth,
permission, device list, adb action, frame stream) is monkeypatched, so
no server, adb or real socket is touched.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketState

from octop.api.routers.mobile import stream as mobile_stream


class _ScriptedWS:
    """WebSocket double that replays scripted client frames and records sends."""

    def __init__(self, frames: list[str], *, app: Any = None) -> None:
        self.application_state = WebSocketState.CONNECTED
        self.app = app
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self.received = 0
        self._frames = list(frames)

    async def accept(self) -> None:
        self.application_state = WebSocketState.CONNECTED

    async def receive_text(self) -> str:
        if not self._frames:
            # The script ran dry: behave like a client that went away, which is
            # the only other way out of the receive loop.
            raise WebSocketDisconnect()
        self.received += 1
        return self._frames.pop(0)

    async def send_text(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        self.application_state = WebSocketState.DISCONNECTED


def _drive(
    monkeypatch: pytest.MonkeyPatch,
    frames: list[str],
    *,
    handled: list[dict[str, Any]],
    timeout: float = 6.0,
) -> _ScriptedWS:
    """Run the route over *frames*; a handler that never returns is a failure."""
    monkeypatch.setattr(mobile_stream, "resolve_request_locale", lambda _ws: "en")
    monkeypatch.setattr(
        mobile_stream,
        "mobile_status",
        lambda *_a, **_k: SimpleNamespace(
            setup_state="ready", ok=True, reason="", selected_device="emulator-5554"
        ),
    )
    monkeypatch.setattr(
        mobile_stream, "resolve_user_from_token", lambda *_a, **_k: SimpleNamespace(id=7)
    )
    monkeypatch.setattr(mobile_stream, "user_has_permission", lambda *_a, **_k: True)
    monkeypatch.setattr(mobile_stream, "set_mobile_agent_control", lambda **_k: None)
    monkeypatch.setattr(
        mobile_stream, "clear_mobile_agent_control_if_device", lambda *_a, **_k: None
    )

    async def fake_handle_input(_ws: Any, msg: dict[str, Any], **_kwargs: Any) -> None:
        handled.append(msg)

    monkeypatch.setattr(mobile_stream, "_handle_input", fake_handle_input)

    async def idle_stream(*_args: Any, **_kwargs: Any) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(mobile_stream, "_stream_frames", idle_stream)

    server = SimpleNamespace(services=SimpleNamespace(config=object()))
    ws = _ScriptedWS(
        frames,
        app=SimpleNamespace(state=SimpleNamespace(octop_server=server)),
    )

    async def main() -> None:
        await asyncio.wait_for(
            mobile_stream.mobile_stream_ws(ws, token=None),
            timeout=timeout,
        )

    asyncio.run(main())
    return ws


_START = json.dumps(
    {
        "type": "start",
        "token": "tok",
        "device": "emulator-5554",
        "codec": "jpeg",
        "quality": 80,
        "max_fps": 10,
        "max_side": 1080,
    }
)
_CLICK = json.dumps({"type": "click", "x": 1, "y": 2})
_STOP = json.dumps({"type": "stop"})


@pytest.mark.parametrize(
    "malformed",
    [
        "",
        "null",
        "123",
        "[1,2]",
        '{"type":"click"',
    ],
)
def test_mobile_stream_ws_ignores_a_malformed_frame(
    monkeypatch: pytest.MonkeyPatch, malformed: str
) -> None:
    """A frame that does not parse — or does not parse to an object — is skipped.

    ``json.loads`` raised ``JSONDecodeError`` and the following ``msg.get`` raised
    ``AttributeError`` *outside* the ``except Exception`` that guards ``_handle_input``,
    so either one escaped the receive loop, hit the handler's outer ``except Exception``,
    and tore the session down in ``finally``: the frame stream was cancelled, the device
    binding cleared, and the socket closed with no error frame. Both cases ``continue``.
    """
    handled: list[dict[str, Any]] = []
    # A valid click *after* the bad frame: if the loop died on it, this never arrives.
    _drive(monkeypatch, [_START, malformed, _CLICK, _STOP], handled=handled)

    assert len(handled) == 1
    assert handled[0]["type"] == "click"


def test_mobile_stream_ws_still_stops_on_a_clean_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard must not swallow the stop frame that ends the loop.

    ``handled`` alone cannot prove this: if ``stop`` were skipped the loop would read
    on until the script ran dry and exit through the same ``WebSocketDisconnect`` path,
    leaving ``handled == ["click"]`` either way. So a click is queued *after* the stop
    and the frame counter is asserted instead — the loop must have consumed exactly
    start, click and stop, and the trailing click must never be read.
    """
    handled: list[dict[str, Any]] = []
    ws = _drive(monkeypatch, [_START, _CLICK, _STOP, _CLICK], handled=handled)

    assert ws.received == 3, "the loop read past the stop frame"
    assert [m["type"] for m in handled] == ["click"]
