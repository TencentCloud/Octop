"""Tests for the desktop stream route's client-frame loop.

The route imports cleanly on its own, so it is driven at unit level with a
scripted WebSocket double and every collaboration point (status probe, auth,
session acquire/release, frame loop) monkeypatched.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketState

from octop.api.routers.desktop import stream as desktop_stream


class _ScriptedWS:
    """WebSocket double that replays scripted client frames and records sends."""

    def __init__(self, frames: list[str], *, app: Any = None) -> None:
        self.application_state = WebSocketState.CONNECTED
        self.app = app
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self._frames = list(frames)

    async def accept(self) -> None:
        self.application_state = WebSocketState.CONNECTED

    async def receive_text(self) -> str:
        if not self._frames:
            raise WebSocketDisconnect()
        return self._frames.pop(0)

    async def send_text(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        self.application_state = WebSocketState.DISCONNECTED

    @property
    def types(self) -> list[str]:
        return [m.get("type") for m in self.sent]


_START = json.dumps({"type": "start", "token": "tok", "monitor": 0, "quality": 80, "max_fps": 10})
_CLICK = json.dumps({"type": "click", "x": 1, "y": 2})
_STOP = json.dumps({"type": "stop"})


def _drive(
    monkeypatch: pytest.MonkeyPatch,
    frames: list[str],
    *,
    handled: list[dict[str, Any]],
    timeout: float = 6.0,
) -> _ScriptedWS:
    """Run the route over *frames*; a handler that never returns is a failure."""
    monkeypatch.setattr(desktop_stream, "resolve_request_locale", lambda _ws: "en")
    monkeypatch.setattr(
        desktop_stream,
        "desktop_status",
        lambda **_k: SimpleNamespace(setup_state="ready", ok=True, reason="", display=":99"),
    )
    monkeypatch.setattr(desktop_stream, "_resolve_display", lambda: ":99")
    monkeypatch.setattr(
        desktop_stream,
        "resolve_user_from_token",
        lambda *_a, **_k: SimpleNamespace(id=7, permissions=["desktop"]),
    )
    monkeypatch.setattr(desktop_stream, "user_has_permission", lambda *_a, **_k: True)

    async def fake_acquire(**_kwargs: Any) -> Any:
        return SimpleNamespace(display=":99", input=object(), capture=object())

    monkeypatch.setattr(desktop_stream, "acquire_session", fake_acquire)

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(desktop_stream, "supersede_user_stream", noop)
    monkeypatch.setattr(desktop_stream, "clear_user_stream", noop)
    monkeypatch.setattr(desktop_stream, "release_session", noop)

    async def fake_handle_input(
        _ws: Any, _session: Any, msg: dict[str, Any], **_kwargs: Any
    ) -> None:
        handled.append(msg)

    monkeypatch.setattr(desktop_stream, "_handle_input", fake_handle_input)

    async def idle_stream(*_args: Any, **_kwargs: Any) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(desktop_stream, "_stream_loop", idle_stream)

    ws = _ScriptedWS(
        frames,
        app=SimpleNamespace(state=SimpleNamespace(octop_server=SimpleNamespace())),
    )

    async def main() -> None:
        await asyncio.wait_for(
            desktop_stream.desktop_stream_ws(ws, token=None),
            timeout=timeout,
        )

    asyncio.run(main())
    return ws


@pytest.mark.parametrize("malformed", ["null", "123", "[1,2]"])
def test_desktop_stream_ws_ignores_a_non_object_frame(
    monkeypatch: pytest.MonkeyPatch, malformed: str
) -> None:
    """A frame that parses to a non-object is skipped, not turned into an error.

    ``json.loads`` was guarded but the following ``msg.get`` was not, so ``null`` /
    ``123`` / ``[1,2]`` raised ``AttributeError`` out of the receive loop, hit the
    handler's outer ``except Exception``, and sent the client an error frame plus a
    ``status: error`` before tearing the session down. The guard has to catch it.
    """
    handled: list[dict[str, Any]] = []
    ws = _drive(monkeypatch, [_START, malformed, _CLICK, _STOP], handled=handled)

    # The click after the bad frame still arrived: the loop survived.
    assert [m["type"] for m in handled] == ["click"]
    assert "error" not in ws.types


def test_desktop_stream_ws_still_stops_on_a_clean_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard must not swallow the stop frame that ends the loop."""
    handled: list[dict[str, Any]] = []
    _drive(monkeypatch, [_START, _CLICK, _STOP], handled=handled)

    assert [m["type"] for m in handled] == ["click"]
