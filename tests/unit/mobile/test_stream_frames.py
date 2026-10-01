"""Tests for the mobile JPEG fallback stream (``_stream_frames``)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from starlette.websockets import WebSocketState

from octop.api.routers.mobile import stream as mobile_stream


class _FakeWS:
    """Minimal WebSocket double: records frames, can drop itself after N frames."""

    def __init__(self, *, stop_after_frames: int | None = None) -> None:
        self.application_state = WebSocketState.CONNECTED
        self.sent: list[dict[str, Any]] = []
        self._stop_after_frames = stop_after_frames

    async def send_text(self, payload: str) -> None:
        message = json.loads(payload)
        self.sent.append(message)
        if self._stop_after_frames is None or message.get("type") != "frame":
            return
        frames = sum(1 for m in self.sent if m.get("type") == "frame")
        if frames >= self._stop_after_frames:
            self.application_state = WebSocketState.DISCONNECTED

    @property
    def types(self) -> list[str]:
        return [m.get("type") for m in self.sent]


def _run(
    ws: _FakeWS,
    *,
    frame_dims: list[int] | None = None,
    timeout: float = 6.0,
) -> None:
    """Drive ``_stream_frames`` to completion; a stream that never ends is a failure."""
    asyncio.run(
        asyncio.wait_for(
            mobile_stream._stream_frames(
                ws,
                device="emulator-5554",
                quality=80,
                max_fps=20.0,
                max_side=1080,
                frame_dims=frame_dims if frame_dims is not None else [0, 0],
            ),
            timeout=timeout,
        )
    )


def test_stream_frames_stops_and_reports_after_persistent_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead device must end the stream with one error frame, not spin forever.

    ``capture_jpeg_frame`` failing on every call is exactly what an unplugged
    phone or a dead adb bridge looks like. The desktop stream stops after a run
    of consecutive misses and tells the client; this JPEG fallback used to retry
    at the frame interval indefinitely, flooding the log while the canvas stayed
    frozen on its last frame with no explanation.
    """
    monkeypatch.setattr(mobile_stream, "find_adb", lambda: None)
    monkeypatch.setattr(mobile_stream, "capture_jpeg_frame", lambda *_a, **_k: None)

    ws = _FakeWS()
    _run(ws)

    assert ws.types == ["error"]
    assert "capture" in str(ws.sent[0]["message"])


def test_stream_frames_keeps_going_when_misses_are_not_consecutive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An occasional dropped frame must not tear the stream down."""
    monkeypatch.setattr(mobile_stream, "find_adb", lambda: None)

    calls = {"n": 0}

    def fake_capture(*_args: object, **_kwargs: object) -> tuple[bytes, int, int, int, int] | None:
        calls["n"] += 1
        if calls["n"] % 2 == 1:
            return None
        return (b"jpeg-bytes", 10, 20, 1080, 1920)

    monkeypatch.setattr(mobile_stream, "capture_jpeg_frame", fake_capture)

    frame_dims = [0, 0]
    ws = _FakeWS(stop_after_frames=4)
    _run(ws, frame_dims=frame_dims)

    assert ws.types == ["frame"] * 4
    assert frame_dims == [1080, 1920]
