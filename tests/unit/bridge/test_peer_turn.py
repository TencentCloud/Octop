"""Peer turn.start should keep dashboard composer fields."""

from __future__ import annotations

import pytest

from octop.api.bridge_peer import prepare_peer_dashboard_turn
from octop.api.routers.chat.models import UserTurnWsFrame
from octop.infra.bridge.manager import _bridge_turn_ws_payload
from octop.infra.bridge.peer_turn import (
    USER_TURN_WS_KEYS,
    PeerTurnRejected,
    peer_turn_relay_finished,
)


def test_bridge_turn_ws_payload_keeps_composer_fields() -> None:
    out = _bridge_turn_ws_payload(
        {
            "type": "turn.start",
            "request_id": "r1",
            "agent_id": "main",
            "text": "hi",
            "thread_id": "thr_1",
            "knowledge_base_ids": ["kb1"],
            "hitl_policy": {"mode": "allow_all"},
            "conversation_mode": "ask",
            "reasoning_mode": "enabled",
            "target_agent_ids": ["doctor"],
            "mcp_servers": ["gmail"],
            "skills": ["notes"],
        }
    )
    assert out["type"] == "user_turn"
    assert out["text"] == "hi"
    assert out["thread_id"] == "thr_1"
    assert out["knowledge_base_ids"] == ["kb1"]
    assert out["hitl_policy"] == {"mode": "allow_all"}
    assert out["conversation_mode"] == "ask"
    assert out["reasoning_mode"] == "enabled"
    assert out["target_agent_ids"] == ["doctor"]
    assert out["mcp_servers"] == ["gmail"]
    assert out["skills"] == ["notes"]
    assert "request_id" not in out
    assert "agent_id" not in out


def test_bridge_turn_ws_payload_defaults_empty_text() -> None:
    out = _bridge_turn_ws_payload({"messages": [{"role": "user", "content": "x"}]})
    assert out["type"] == "user_turn"
    assert out["text"] == ""
    assert out["messages"][0]["content"] == "x"


def test_peer_turn_relay_waits_for_turn_ended() -> None:
    assert peer_turn_relay_finished("done") is False
    assert peer_turn_relay_finished("token") is False
    assert peer_turn_relay_finished("turn.ended") is True
    assert peer_turn_relay_finished("error") is True


def test_user_turn_ws_keys_match_dashboard_frame() -> None:
    frame_keys = set(UserTurnWsFrame.model_fields) - {"type"}
    assert frame_keys == USER_TURN_WS_KEYS


@pytest.mark.asyncio
async def test_empty_peer_turn_is_rejected() -> None:
    with pytest.raises(PeerTurnRejected, match="empty message"):
        await prepare_peer_dashboard_turn(
            server=object(),
            user=object(),
            agent_id="a1",
            payload={},
            ws_connection_id="ws",
        )


@pytest.mark.asyncio
async def test_prepare_peer_turn_admits_steer_when_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    from octop.api.routers.chat.turn import PreparedDashboardTurn
    from octop.infra.gateway.steer import SteerCoordinator

    steer = SteerCoordinator()
    steer.begin_turn("thr-1")
    pushed: list[dict[str, object]] = []

    class _Hub:
        def is_turn_active(self, thread_id: str) -> bool:
            return thread_id == "thr-1"

        async def push_to_thread(self, thread_id: str, frame: dict[str, object]) -> None:
            assert thread_id == "thr-1"
            pushed.append(frame)

    gateway = MagicMock()
    gateway.steer = steer
    gateway.ws_hub = _Hub()
    gateway.processor = None
    runtime = MagicMock()
    runtime.gateway = gateway
    server = MagicMock()
    server.app_runtime = runtime

    async def _fake_prepare(*_args: object, **_kwargs: object) -> PreparedDashboardTurn:
        return PreparedDashboardTurn(
            thread_id="thr-1",
            session_key="sk",
            mcp_servers=None,
            skills=None,
            model_ref=None,
            inbound_content=[],
            composer_context=None,
            inbound_attachments=[],
        )

    monkeypatch.setattr("octop.api.bridge_peer.prepare_dashboard_turn", _fake_prepare)
    build = MagicMock()
    monkeypatch.setattr("octop.api.bridge_peer.build_dashboard_inbound", build)

    class _User:
        id = 1
        is_admin = False

    result = await prepare_peer_dashboard_turn(
        server=server,
        user=_User(),
        agent_id="a1",
        payload={
            "text": "use plan B",
            "thread_id": "thr-1",
            "delivery": "auto",
            "client_pending_id": "cp1",
        },
        ws_connection_id="ws",
    )
    assert result.thread_id == "thr-1"
    assert result.inbound is None
    build.assert_not_called()
    types = [str(frame.get("type") or "") for frame in pushed]
    assert "steer.ack" in types
    assert "steer.queued" in types


@pytest.mark.asyncio
async def test_prepare_peer_turn_enqueues_when_hub_turn_is_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import MagicMock

    from octop.api.routers.chat.turn import PreparedDashboardTurn
    from octop.infra.gateway.steer import SteerCoordinator

    steer = SteerCoordinator()
    steer.begin_turn("thr-1")

    class _Hub:
        def is_turn_active(self, _thread_id: str) -> bool:
            return False

        async def push_to_thread(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("idle room must enqueue, not steer")

    gateway = MagicMock()
    gateway.steer = steer
    gateway.ws_hub = _Hub()
    gateway.processor = None
    runtime = MagicMock()
    runtime.gateway = gateway
    server = MagicMock()
    server.app_runtime = runtime

    async def _fake_prepare(*_args: object, **_kwargs: object) -> PreparedDashboardTurn:
        return PreparedDashboardTurn(
            thread_id="thr-1",
            session_key="sk",
            mcp_servers=None,
            skills=None,
            model_ref=None,
            inbound_content=[],
            composer_context=None,
            inbound_attachments=[],
        )

    monkeypatch.setattr("octop.api.bridge_peer.prepare_dashboard_turn", _fake_prepare)
    inbound = object()
    monkeypatch.setattr(
        "octop.api.bridge_peer.build_dashboard_inbound",
        MagicMock(return_value=inbound),
    )

    class _User:
        id = 1
        is_admin = False

    result = await prepare_peer_dashboard_turn(
        server=server,
        user=_User(),
        agent_id="a1",
        payload={"text": "next question", "thread_id": "thr-1"},
        ws_connection_id="ws",
    )
    assert result.inbound is inbound


@pytest.mark.asyncio
async def test_execute_peer_turn_skips_enqueue_when_steered() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from octop.api.bridge_peer import PreparedPeerTurn
    from octop.infra.bridge.manager import BridgeManager
    from octop.infra.bridge.transport import BridgeSession

    sent: list[dict[str, object]] = []

    async def capture(payload: dict[str, object]) -> None:
        sent.append(payload)

    sess = BridgeSession(connection_id="cid1", send_text=AsyncMock())
    sess.send_json = capture  # type: ignore[method-assign]

    user = MagicMock()
    user.id = 1
    runtime = MagicMock()
    runtime.user_manager.get_by_id.return_value = user
    runtime.gateway.channel_manager.enqueue = MagicMock()
    runtime.gateway.ws_hub.register = MagicMock()
    runtime.gateway.ws_hub.subscribe = MagicMock()
    runtime.gateway.ws_hub.unregister = MagicMock()
    server = MagicMock()
    server.app_runtime = runtime
    app = MagicMock()
    app.state.octop_server = server

    async def runner(**_kwargs: object) -> PreparedPeerTurn:
        return PreparedPeerTurn(thread_id="thr-1", inbound=None)

    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    mgr.bind_asgi_app(app, peer_turn_runner=runner)
    mgr._sessions["cid1"] = sess
    mgr._repo.get = MagicMock(return_value=MagicMock(owner_user_id=1))  # type: ignore[method-assign]

    await mgr._execute_peer_turn(
        "cid1",
        {"request_id": "r1", "agent_id": "agent", "text": "steer me"},
    )
    runtime.gateway.channel_manager.enqueue.assert_not_called()
    runtime.gateway.ws_hub.subscribe.assert_not_called()
    assert sent == [{"type": "turn.end", "request_id": "r1"}]


@pytest.mark.asyncio
async def test_execute_peer_cancel_stops_host_stream() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from octop.infra.bridge.manager import BridgeManager
    from octop.infra.bridge.transport import BridgeSession

    thread = MagicMock()
    thread.agent_id = "agent"
    thread.user_id = 1
    discarded = MagicMock(
        seq=2,
        client_pending_ids=["c1"],
        pending_ids=["p1"],
        turn_id="t1",
        reason="turn_cancelled",
    )
    gateway = MagicMock()
    gateway.thread_registry.get_thread.return_value = thread
    gateway.steer.discard.return_value = discarded
    gateway.ws_hub.push_to_thread = AsyncMock()

    user = MagicMock()
    user.id = 1
    runtime = MagicMock()
    runtime.user_manager.get_by_id.return_value = user
    runtime.gateway = gateway
    server = MagicMock()
    server.app_runtime = runtime
    app = MagicMock()
    app.state.octop_server = server

    sent: list[dict[str, object]] = []

    async def capture(payload: dict[str, object]) -> None:
        sent.append(payload)

    sess = BridgeSession(connection_id="cid1", send_text=AsyncMock())
    sess.send_json = capture  # type: ignore[method-assign]

    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    mgr._asgi_app = app
    mgr._sessions["cid1"] = sess
    mgr._repo.get = MagicMock(return_value=MagicMock(owner_user_id=1))  # type: ignore[method-assign]

    await mgr._execute_peer_cancel(
        "cid1",
        {"request_id": "r1", "agent_id": "agent", "thread_id": "thr-1"},
    )
    gateway.steer.mark_cancelling.assert_called_once_with("thr-1")
    runtime.agent_registry.cancel_stream.assert_called_once_with("agent", "thr-1")
    gateway.ws_hub.push_to_thread.assert_awaited()
    assert sent[-1] == {"type": "turn.end", "request_id": "r1"}


@pytest.mark.asyncio
async def test_execute_peer_turn_holds_room_until_unlisten() -> None:
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from octop.api.bridge_peer import PreparedPeerTurn
    from octop.infra.bridge.manager import BridgeManager
    from octop.infra.bridge.transport import BridgeSession
    from octop.infra.gateway.ws.ws_hub import WebSocketHub

    sent: list[dict[str, object]] = []

    async def capture(payload: dict[str, object]) -> None:
        sent.append(payload)

    sess = BridgeSession(connection_id="cid1", send_text=AsyncMock())
    sess.send_json = capture  # type: ignore[method-assign]

    hub = WebSocketHub()
    user = MagicMock()
    user.id = 1
    runtime = MagicMock()
    runtime.user_manager.get_by_id.return_value = user
    runtime.gateway.channel_manager.enqueue = MagicMock()
    runtime.gateway.ws_hub = hub
    server = MagicMock()
    server.app_runtime = runtime
    app = MagicMock()
    app.state.octop_server = server

    async def runner(**_kwargs: object) -> PreparedPeerTurn:
        return PreparedPeerTurn(thread_id="thr-1", inbound={"text": "hi"})

    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    mgr.bind_asgi_app(app, peer_turn_runner=runner)
    mgr._sessions["cid1"] = sess
    mgr._repo.get = MagicMock(return_value=MagicMock(owner_user_id=1))  # type: ignore[method-assign]

    turn_task = asyncio.create_task(
        mgr._execute_peer_turn(
            "cid1",
            {"request_id": "r1", "agent_id": "agent", "text": "hi"},
        )
    )
    for _ in range(50):
        subscribed = False
        for item in sent:
            frame = item.get("frame")
            if isinstance(frame, dict) and frame.get("type") == "thread":
                subscribed = True
                break
        if subscribed:
            break
        await asyncio.sleep(0.01)
    await hub.push_to_thread("thr-1", {"type": "turn.ended", "thread_id": "thr-1"})
    await asyncio.sleep(0.05)
    await hub.push_to_thread(
        "thr-1",
        {"type": "token", "agent_id": "doctor", "content": "磁盘还剩 8G"},
    )
    await asyncio.sleep(0.02)
    assert not turn_task.done()
    assert not any(item.get("type") == "turn.end" for item in sent)
    mgr._stop_peer_listen("r1")
    await asyncio.wait_for(turn_task, timeout=1.0)
    frames = [
        item["frame"]
        for item in sent
        if item.get("type") == "turn.chunk" and isinstance(item.get("frame"), dict)
    ]
    assert any(frame.get("type") == "turn.ended" for frame in frames)
    assert any(frame.get("content") == "磁盘还剩 8G" for frame in frames)
    assert sent[-1] == {"type": "turn.end", "request_id": "r1"}
