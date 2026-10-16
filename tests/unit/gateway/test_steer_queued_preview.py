"""Live ``steer.queued`` must carry the same preview the snapshot replays.

Admission stores ``PendingSteer.preview`` (text, else the first attachment name);
the live frame re-derived it from ``text`` only, so an attachment-only steer
showed an empty bubble until a reconnect replayed the snapshot with a filename.
"""

from __future__ import annotations

from typing import Any

import pytest

from octop.api.routers.chat.ws import _maybe_admit_steer
from octop.infra.gateway.steer.coordinator import SteerCoordinator


class _Hub:
    def __init__(self) -> None:
        self.pushed: list[dict[str, Any]] = []

    async def push_to_thread(self, thread_id: str, frame: dict[str, Any]) -> None:
        self.pushed.append(frame)


@pytest.mark.asyncio
async def test_queued_frame_preview_matches_snapshot() -> None:
    coordinator = SteerCoordinator()
    turn_id, _seq, _ = coordinator.begin_turn("t1")
    hub = _Hub()
    acks: list[dict[str, Any]] = []

    async def send_frame(frame: dict[str, Any]) -> None:
        acks.append(frame)

    blocks = [
        {
            "type": "image",
            "workspace_path": "inbound/shot.png",
            "filename": "shot.png",
            "media_type": "image/png",
        }
    ]
    handled = await _maybe_admit_steer(
        text="",
        thread_id="t1",
        delivery="steer",
        client_pending_id="c1",
        expected_turn_id=turn_id,
        steer=coordinator,
        hub=hub,
        send_frame=send_frame,
        hitl_paused=False,
        content_blocks=blocks,
    )
    assert handled
    queued = next(f for f in hub.pushed if f["type"] == "steer.queued")
    snapshot = coordinator.snapshot_frames("t1")[0]
    assert queued["preview"] == snapshot["items"][0]["preview"] == "shot.png"
