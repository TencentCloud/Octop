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
async def test_relay_user_turn_closes_generating_when_peer_stops_at_done() -> None:
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

    async def send_json(payload: dict[str, Any]) -> None:
        if payload.get("type") != "turn.start":
            return
        request_id = str(payload["request_id"])
        queue = mgr._turn_waiters[request_id]
        await queue.put(
            {
                "type": "turn.chunk",
                "request_id": request_id,
                "frame": {"type": "turn.started", "turn_id": "t1"},
            }
        )
        await queue.put(
            {
                "type": "turn.chunk",
                "request_id": request_id,
                "frame": {"type": "done"},
            }
        )
        await queue.put({"type": "turn.end", "request_id": request_id})

    sess.send_json = send_json  # type: ignore[method-assign]
    frames: list[dict[str, Any]] = []

    async def on_frame(frame: dict[str, Any]) -> None:
        frames.append(frame)

    await mgr.relay_user_turn(
        connection_id="cid1",
        owner_user_id=1,
        remote_agent_id="agent",
        turn_payload={"text": "hi"},
        on_frame=on_frame,
    )
    assert [frame["type"] for frame in frames] == ["turn.started", "done", "turn.ended"]


@pytest.mark.asyncio
async def test_relay_user_turn_unlistens_when_cancelled() -> None:
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
    started = asyncio.Event()
    sent: list[str] = []

    async def send_json(payload: dict[str, Any]) -> None:
        sent.append(str(payload.get("type") or ""))
        if payload.get("type") == "turn.start":
            started.set()
            request_id = str(payload["request_id"])
            queue = mgr._turn_waiters[request_id]
            await queue.put(
                {
                    "type": "turn.chunk",
                    "request_id": request_id,
                    "frame": {"type": "turn.ended", "thread_id": "thr-1"},
                }
            )
            return
        if payload.get("type") == "turn.unlisten":
            request_id = str(payload["request_id"])
            queue = mgr._turn_waiters.get(request_id)
            if queue is not None:
                await queue.put({"type": "turn.end", "request_id": request_id})

    sess.send_json = send_json  # type: ignore[method-assign]
    frames: list[dict[str, Any]] = []

    async def on_frame(frame: dict[str, Any]) -> None:
        frames.append(frame)

    task = asyncio.create_task(
        mgr.relay_user_turn(
            connection_id="cid1",
            owner_user_id=1,
            remote_agent_id="agent",
            turn_payload={"text": "hi"},
            on_frame=on_frame,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1.0)
    await asyncio.sleep(0.02)
    assert [frame["type"] for frame in frames] == ["turn.ended"]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "turn.unlisten" in sent


@pytest.mark.asyncio
async def test_relay_user_listen_forwards_member_frames_until_unlisten() -> None:
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
    started = asyncio.Event()

    async def send_json(payload: dict[str, Any]) -> None:
        if payload.get("type") == "turn.listen":
            started.set()
            request_id = str(payload["request_id"])
            queue = mgr._turn_waiters[request_id]
            await queue.put(
                {
                    "type": "turn.chunk",
                    "request_id": request_id,
                    "frame": {
                        "type": "turn_status",
                        "thread_id": "thr-room",
                        "active": False,
                    },
                }
            )
            await queue.put(
                {
                    "type": "turn.chunk",
                    "request_id": request_id,
                    "frame": {
                        "type": "token",
                        "agent_id": "doctor",
                        "content": "磁盘还剩 8G",
                    },
                }
            )
            return
        if payload.get("type") == "turn.unlisten":
            request_id = str(payload["request_id"])
            queue = mgr._turn_waiters[request_id]
            await queue.put({"type": "turn.end", "request_id": request_id})

    sess.send_json = send_json  # type: ignore[method-assign]
    frames: list[dict[str, Any]] = []

    async def on_frame(frame: dict[str, Any]) -> None:
        frames.append(frame)

    task = asyncio.create_task(
        mgr.relay_user_listen(
            connection_id="cid1",
            owner_user_id=1,
            remote_agent_id="host",
            thread_id="thr-room",
            on_frame=on_frame,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1.0)
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [frame.get("type") for frame in frames][:2] == ["turn_status", "token"]
    assert frames[1].get("content") == "磁盘还剩 8G"


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


def _bridge_row() -> Any:
    from octop.infra.db.repos.bridge_connections import BridgeConnectionRow

    return BridgeConnectionRow(
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


@pytest.mark.asyncio
async def test_relay_turn_cancel_sends_control_and_forwards_end() -> None:
    from octop.infra.bridge.manager import BridgeManager
    from octop.infra.bridge.transport import FEATURE_TURN_CONTROL

    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    mgr.get_owned = MagicMock(return_value=_bridge_row())  # type: ignore[method-assign]
    sess = BridgeSession(
        connection_id="cid1",
        send_text=AsyncMock(),
        peer_features={FEATURE_TURN_CONTROL},
    )
    mgr._sessions["cid1"] = sess
    sent: list[dict[str, Any]] = []

    async def send_json(payload: dict[str, Any]) -> None:
        sent.append(payload)
        if payload.get("type") != "turn.cancel":
            return
        request_id = str(payload["request_id"])
        queue = mgr._turn_waiters[request_id]
        await queue.put({"type": "turn.end", "request_id": request_id})

    sess.send_json = send_json  # type: ignore[method-assign]
    frames: list[dict[str, Any]] = []
    await mgr.relay_turn_cancel(
        connection_id="cid1",
        owner_user_id=1,
        remote_agent_id="agent",
        thread_id="thr-1",
        on_frame=frames.append,
    )
    assert sent[0]["type"] == "turn.cancel"
    assert sent[0]["thread_id"] == "thr-1"
    assert sent[0]["agent_id"] == "agent"
    assert frames == []


@pytest.mark.asyncio
async def test_relay_turn_steer_remove_forwards_ack() -> None:
    from octop.infra.bridge.manager import BridgeManager
    from octop.infra.bridge.transport import FEATURE_TURN_CONTROL

    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    mgr.get_owned = MagicMock(return_value=_bridge_row())  # type: ignore[method-assign]
    sess = BridgeSession(
        connection_id="cid1",
        send_text=AsyncMock(),
        peer_features={FEATURE_TURN_CONTROL},
    )
    mgr._sessions["cid1"] = sess

    async def send_json(payload: dict[str, Any]) -> None:
        if payload.get("type") != "turn.steer_remove":
            return
        request_id = str(payload["request_id"])
        queue = mgr._turn_waiters[request_id]
        await queue.put(
            {
                "type": "turn.chunk",
                "request_id": request_id,
                "frame": {
                    "type": "steer.ack",
                    "status": "removed",
                    "client_pending_id": "cp1",
                },
            }
        )
        await queue.put({"type": "turn.end", "request_id": request_id})

    sess.send_json = send_json  # type: ignore[method-assign]
    frames: list[dict[str, Any]] = []

    async def on_frame(frame: dict[str, Any]) -> None:
        frames.append(frame)

    await mgr.relay_turn_steer_remove(
        connection_id="cid1",
        owner_user_id=1,
        remote_agent_id="agent",
        payload={
            "thread_id": "thr-1",
            "turn_id": "t1",
            "client_pending_id": "cp1",
            "pending_id": "p1",
        },
        on_frame=on_frame,
    )
    assert frames == [
        {"type": "steer.ack", "status": "removed", "client_pending_id": "cp1"},
    ]


@pytest.mark.asyncio
async def test_relay_turn_cancel_fails_fast_without_peer_feature() -> None:
    from octop.infra.bridge.manager import BridgeManager

    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    mgr.get_owned = MagicMock(return_value=_bridge_row())  # type: ignore[method-assign]
    sess = BridgeSession(connection_id="cid1", send_text=AsyncMock())
    mgr._sessions["cid1"] = sess
    sent: list[dict[str, Any]] = []
    sess.send_json = AsyncMock(side_effect=lambda payload: sent.append(payload))  # type: ignore[method-assign]
    frames: list[dict[str, Any]] = []

    async def on_frame(frame: dict[str, Any]) -> None:
        frames.append(frame)

    await mgr.relay_turn_cancel(
        connection_id="cid1",
        owner_user_id=1,
        remote_agent_id="agent",
        thread_id="thr-1",
        on_frame=on_frame,
    )
    assert sent == []
    assert frames == [{"type": "error", "message": "peer does not support turn.cancel"}]
