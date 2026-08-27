"""Dashboard notification WebSocket for text-type pushes."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.support.app import octop_client
from tests.support.auth import auth_header, bootstrap_admin, ensure_users
from tests.support.http import ws_token


@pytest.fixture
async def env(tmp_octop_home: Path) -> AsyncIterator[Any]:
    async with octop_client(tmp_octop_home) as (c, srv):
        await bootstrap_admin(c, tmp_octop_home)
        admin_auth = await auth_header(c)
        users = await ensure_users(c, admin_auth, "alice", "bob")
        yield c, srv, users["alice"], users["bob"]


async def test_notifications_ws_ping_pong(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth = env
    with TestClient(c._octop_app).websocket_connect(  # type: ignore[attr-defined]
        f"/api/notifications/ws?token={ws_token(alice_auth)}"
    ) as ws:
        ws.send_json({"type": "ping"})
        assert json.loads(ws.receive_text()) == {"type": "pong"}


async def test_notifications_ws_missing_token_rejected(env: Any) -> None:
    c, _srv, _alice_auth, _bob_auth = env
    with (
        pytest.raises(WebSocketDisconnect),
        TestClient(c._octop_app).websocket_connect("/api/notifications/ws"),  # type: ignore[attr-defined]
    ):
        pass


async def test_notifications_ws_receives_user_push(env: Any) -> None:
    c, srv, alice_auth, _bob_auth = env
    user = srv.user_manager.get("alice")
    assert user is not None
    token = ws_token(alice_auth)
    connected = threading.Event()
    frames: list[dict[str, object]] = []
    errors: list[BaseException] = []

    def _session() -> None:
        try:
            with TestClient(c._octop_app).websocket_connect(  # type: ignore[attr-defined]
                f"/api/notifications/ws?token={token}"
            ) as ws:
                ws.send_json({"type": "ping"})
                pong = json.loads(ws.receive_text())
                if pong != {"type": "pong"}:
                    raise AssertionError(f"unexpected pong: {pong!r}")
                connected.set()
                frames.append(json.loads(ws.receive_text()))
        except BaseException as exc:
            errors.append(exc)
            connected.set()

    session_task = asyncio.create_task(asyncio.to_thread(_session))
    assert await asyncio.to_thread(connected.wait, 5)
    if errors:
        raise errors[0]
    await srv.app_runtime.gateway.ws_hub.push_to_user(
        user.id,
        {
            "type": "dashboard_push",
            "agent_id": "a1",
            "thread_id": "thr_1",
            "text": "记得喝水",
            "agent_name": "助手",
        },
    )
    await asyncio.wait_for(session_task, timeout=5)
    assert frames == [
        {
            "type": "dashboard_push",
            "agent_id": "a1",
            "thread_id": "thr_1",
            "text": "记得喝水",
            "agent_name": "助手",
        }
    ]
