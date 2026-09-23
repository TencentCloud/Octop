"""Faster preview frames must not multiply expensive tab/status polling."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketState

from octop.api.routers.browser import stream


@pytest.mark.asyncio
async def test_frames_refresh_independently_of_session_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = SimpleNamespace(application_state=WebSocketState.CONNECTED)
    now = 10.0
    frames = 0

    async def capture(_sess: object) -> str:
        nonlocal now, frames
        frames += 1
        now += 0.01
        if frames == 15:
            ws.application_state = WebSocketState.DISCONNECTED
        return "jpeg"

    async def sleep(delay: float) -> None:
        nonlocal now
        now += delay

    snapshot = AsyncMock()
    monkeypatch.setattr(stream, "_send_json", AsyncMock())
    monkeypatch.setattr(stream, "_send_session_snapshot", snapshot)
    monkeypatch.setattr(stream, "_capture_jpeg", capture)
    monkeypatch.setattr(stream.time, "monotonic", lambda: now)
    monkeypatch.setattr(stream.asyncio, "sleep", sleep)
    await stream._stream_loop(ws, object(), "test", listen_only=False)  # type: ignore[arg-type]
    assert frames == 15
    assert snapshot.await_count == 2
    assert now - 10.0 == pytest.approx(15 / 12)
