"""Screencast frame handler: ack binds to the CDP client captured at
registration (a tab switch replaces sess._internal.client — acking via the
new client would stall the old screencast session)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from octop.api.routers.browser import stream as stream_mod
from starlette.websockets import WebSocketState


class _FakeWs:
    application_state = WebSocketState.CONNECTED

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def send_text(self, raw: str) -> None:
        import json

        self.sent.append(json.loads(raw))


def _fake_client() -> SimpleNamespace:
    return SimpleNamespace(
        send=AsyncMock(return_value={}),
        send_no_wait=AsyncMock(return_value={}),
        on=AsyncMock(),
        off=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_ack_goes_to_captured_client_not_current_session_client() -> None:
    """After a tab switch the ack must still use the original client."""
    captured = _fake_client()
    ws = _FakeWs()
    handler = stream_mod._make_screencast_handler(captured, ws)

    # Simulate the tab switch: the session now points at a *different* client.
    sess = SimpleNamespace(_internal=SimpleNamespace(client=_fake_client()))
    # Handler captured the old client at registration; it never reads the session.
    await handler({"data": "AA==", "sessionId": 7})

    captured.send_no_wait.assert_awaited_once_with(
        "Page.screencastFrameAck", {"sessionId": 7}
    )
    # The *current* session client must NOT have been used for the ack.
    assert sess._internal.client.send_no_wait.await_count == 0
    # Frame forwarded regardless.
    assert ws.sent == [{"type": "frame", "data": "AA=="}]


@pytest.mark.asyncio
async def test_ack_sent_before_frame_forward() -> None:
    """Ack first, forward second — WS backpressure must never delay the ack."""
    captured = _fake_client()
    ws = _FakeWs()
    handler = stream_mod._make_screencast_handler(captured, ws)
    await handler({"data": "BB==", "sessionId": 9})

    # ack call happened (send_no_wait) and frame was forwarded
    captured.send_no_wait.assert_awaited()
    assert ws.sent == [{"type": "frame", "data": "BB=="}]


@pytest.mark.asyncio
async def test_ack_without_session_id_is_skipped() -> None:
    captured = _fake_client()
    handler = stream_mod._make_screencast_handler(captured, _FakeWs())
    await handler({"data": "CC=="})  # no sessionId
    captured.send_no_wait.assert_not_called()


@pytest.mark.asyncio
async def test_start_and_stop_manage_handlers_per_client() -> None:
    """_start_screencast registers per client; _stop_screencast detaches every
    registered handler, including ones on replaced clients."""
    client = _fake_client()
    sess = SimpleNamespace(_internal=SimpleNamespace(client=client))
    ws = _FakeWs()

    ok = await stream_mod._start_screencast(sess, ws, width=1280, height=800)
    assert ok is True
    client.on.assert_called_once()
    assert len(stream_mod._screencast_handlers) == 1

    # A tab switch replaces the client and restarts screencast on it.
    client2 = _fake_client()
    sess2 = SimpleNamespace(_internal=SimpleNamespace(client=client2))
    ok2 = await stream_mod._start_screencast(sess2, ws, width=1280, height=800)
    assert ok2 is True
    assert len(stream_mod._screencast_handlers) == 2  # both tracked

    await stream_mod._stop_screencast(sess2)
    assert len(stream_mod._screencast_handlers) == 0  # all detached
    client.off.assert_called_once()  # old client handler removed too
    client2.off.assert_called_once()
