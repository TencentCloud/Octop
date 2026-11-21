"""Faster preview frames must not multiply expensive tab/status polling."""

from unittest.mock import AsyncMock

import pytest

from octop.api.routers.browser import stream


@pytest.mark.asyncio
async def test_frames_refresh_independently_of_session_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 10.0
    frames = 0

    async def capture(_sess: object) -> str:
        nonlocal now, frames
        frames += 1
        now += 0.01
        return "jpeg"

    async def sleep(delay: float) -> None:
        nonlocal now
        now += delay

    snapshot = AsyncMock()
    send_json = AsyncMock()
    monkeypatch.setattr(stream, "_send_session_snapshot", snapshot)
    monkeypatch.setattr(stream, "_capture_jpeg", capture)
    monkeypatch.setattr(stream.time, "monotonic", lambda: now)
    monkeypatch.setattr(stream.asyncio, "sleep", sleep)
    await stream._stream_loop(send_json, lambda: frames < 15, object(), "test", listen_only=False)
    assert frames == 15
    assert sum(call.args[0]["type"] == "frame" for call in send_json.await_args_list) == 15
    assert snapshot.await_count == 2
    assert now - 10.0 == pytest.approx(15 / 12)
