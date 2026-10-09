"""BridgeSession heartbeat and half-open detection."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.bridge.transport import BridgeSession
from octop.infra.errors import ErrorCode, OctopError


@pytest.mark.asyncio
async def test_ping_replies_with_pong() -> None:
    sent: list[str] = []

    async def capture(text: str) -> None:
        sent.append(text)

    sess = BridgeSession(connection_id="c1", send_text=capture)
    await sess.handle_message(json.dumps({"type": "ping"}))
    assert json.loads(sent[-1]) == {"type": "pong"}
    assert sess.closed is False


@pytest.mark.asyncio
async def test_pong_enables_stale_detection() -> None:
    async def noop(_text: str) -> None:
        return None

    sess = BridgeSession(connection_id="c1", send_text=noop)
    assert sess.is_stale(timeout=0.0) is False
    await sess.handle_message(json.dumps({"type": "pong"}))
    sess._last_recv = 0.0  # noqa: SLF001 — force idle
    assert sess.is_stale(timeout=0.0) is True


@pytest.mark.asyncio
async def test_heartbeat_timeout_closes_after_seen_pong() -> None:
    async def noop(_text: str) -> None:
        return None

    closed = asyncio.Event()

    async def close_transport() -> None:
        closed.set()

    sess = BridgeSession(connection_id="c1", send_text=noop, close_transport=close_transport)
    await sess.handle_message(json.dumps({"type": "pong"}))
    sess.start_heartbeat(interval=0.01, timeout=0.03)
    await asyncio.wait_for(sess.wait_closed(), timeout=1.0)
    assert sess.closed is True
    assert sess.close_reason == "heartbeat timeout"
    assert closed.is_set()


@pytest.mark.asyncio
async def test_heartbeat_does_not_close_old_peer_without_pong() -> None:
    sent: list[str] = []

    async def capture(text: str) -> None:
        sent.append(text)

    sess = BridgeSession(connection_id="c1", send_text=capture)
    sess.start_heartbeat(interval=0.02, timeout=0.05)
    await asyncio.sleep(0.08)
    assert sess.closed is False
    assert any(json.loads(item).get("type") == "ping" for item in sent)
    await sess.close()


@pytest.mark.asyncio
async def test_tunnel_request_does_not_block_ping() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    sent: list[dict[str, Any]] = []

    async def capture(text: str) -> None:
        sent.append(json.loads(text))

    async def handler(_payload: dict[str, Any]) -> dict[str, Any]:
        started.set()
        await release.wait()
        return {"status": 200, "headers": {}, "done": True}

    sess = BridgeSession(connection_id="c1", send_text=capture, on_tunnel_request=handler)
    await sess.handle_message(
        json.dumps({"type": "tunnel.request", "id": "1", "method": "GET", "path": "/"})
    )
    await asyncio.wait_for(started.wait(), timeout=0.5)
    await sess.handle_message(json.dumps({"type": "ping"}))
    assert sent[-1] == {"type": "pong"}
    release.set()
    await asyncio.sleep(0.05)
    assert any(item.get("type") == "tunnel.response" for item in sent)
    await sess.close()


@pytest.mark.asyncio
async def test_close_fails_pending_tunnel_request() -> None:
    async def hang(_text: str) -> None:
        return None

    sess = BridgeSession(connection_id="c1", send_text=hang)
    task = asyncio.create_task(sess.tunnel_request(method="GET", path="/api/agents", timeout=5.0))
    await asyncio.sleep(0.02)
    await sess.close()
    with pytest.raises(ConnectionError, match="bridge session closed"):
        await task


@pytest.mark.asyncio
async def test_next_queue_item_aborts_when_session_closes() -> None:
    async def noop(_text: str) -> None:
        return None

    sess = BridgeSession(connection_id="c1", send_text=noop)
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    task = asyncio.create_task(sess.next_queue_item(queue, timeout=5.0))
    await asyncio.sleep(0.02)
    await sess.close()
    with pytest.raises(ConnectionError, match="bridge session closed"):
        await task


@pytest.mark.asyncio
async def test_require_live_session_drops_stale_immediately() -> None:
    from octop.infra.bridge.manager import BridgeManager

    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    stale = BridgeSession(connection_id="cid1", send_text=AsyncMock())
    await stale.handle_message(json.dumps({"type": "pong"}))
    stale._last_recv = 0.0  # noqa: SLF001
    mgr._sessions["cid1"] = stale

    with pytest.raises(OctopError) as ei:
        await mgr._require_live_session("cid1")
    assert ei.value.code == ErrorCode.BRIDGE_NOT_CONNECTED
    assert stale.closed is True
    assert "cid1" not in mgr._sessions


@pytest.mark.asyncio
async def test_require_live_session_waits_for_outbound_supervisor() -> None:
    from octop.infra.bridge.manager import BridgeManager

    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    fresh = BridgeSession(connection_id="cid1", send_text=AsyncMock())

    async def restore() -> None:
        await asyncio.sleep(0.05)
        mgr._sessions["cid1"] = fresh

    mgr._client_tasks["cid1"] = asyncio.create_task(asyncio.sleep(2))
    restorer = asyncio.create_task(restore())
    try:
        live = await mgr._require_live_session("cid1")
        assert live is fresh
    finally:
        restorer.cancel()
        mgr._client_tasks["cid1"].cancel()


@pytest.mark.asyncio
async def test_relay_user_turn_fails_fast_when_session_closes() -> None:
    from octop.infra.bridge.manager import BridgeManager
    from octop.infra.db.repos.bridge_connections import BridgeConnectionRow

    row = BridgeConnectionRow(
        pk=1,
        connection_id="cid1",
        owner_user_id=1,
        peer_base_url="https://peer.example",
        peer_username="alice",
        display_name="云端",
        notes=None,
        icon_name=None,
        credential_blob=b"enc",
        access_token_blob=b"tok",
        token_expires_at=None,
        status="connected",
        last_error=None,
        last_seen_at=None,
        auto_reconnect=True,
        created_at=1,
        updated_at=1,
    )
    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    mgr.get_owned = MagicMock(return_value=row)  # type: ignore[method-assign]
    sess = BridgeSession(connection_id="cid1", send_text=AsyncMock())
    mgr._sessions["cid1"] = sess

    async def killer() -> None:
        await asyncio.sleep(0.05)
        await sess.close()

    asyncio.create_task(killer())
    frames: list[dict[str, Any]] = []
    with pytest.raises(OctopError) as exc_info:
        await mgr.relay_user_turn(
            connection_id="cid1",
            owner_user_id=1,
            remote_agent_id="agent",
            turn_payload={"text": "hi"},
            on_frame=frames.append,
        )
    assert exc_info.value.code == ErrorCode.BRIDGE_NOT_CONNECTED
