"""Dashboard notification WebSocket for text-type pushes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.support.app import octop_client
from tests.support.auth import auth_header, bootstrap_admin, ensure_users
from tests.support.http import ws_connect, ws_token


@pytest.fixture
async def env(tmp_octop_home: Path) -> AsyncIterator[Any]:
    async with octop_client(tmp_octop_home) as (c, srv):
        await bootstrap_admin(c, tmp_octop_home)
        admin_auth = await auth_header(c)
        users = await ensure_users(c, admin_auth, "alice", "bob")
        yield c, srv, users["alice"], users["bob"]


def _notifications_ws(c: Any, auth: dict[str, str] | None = None) -> Any:
    query = f"?token={ws_token(auth)}" if auth else ""
    return ws_connect(c._octop_app, f"/api/notifications/ws{query}")


async def test_notifications_ws_ping_pong(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth = env
    async with _notifications_ws(c, alice_auth) as ws:
        await ws.send_json({"type": "ping"})
        assert await ws.receive_json() == {"type": "pong"}


async def test_notifications_ws_missing_token_rejected(env: Any) -> None:
    c, _srv, _alice_auth, _bob_auth = env
    with pytest.raises(WebSocketDisconnect):
        async with _notifications_ws(c):
            pass


async def test_notifications_ws_receives_user_push(env: Any) -> None:
    c, srv, alice_auth, _bob_auth = env
    user = srv.user_manager.get("alice")
    assert user is not None

    async with _notifications_ws(c, alice_auth) as ws:
        await ws.send_json({"type": "ping"})
        assert await ws.receive_json() == {"type": "pong"}
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
        assert await ws.receive_json() == {
            "type": "dashboard_push",
            "agent_id": "a1",
            "thread_id": "thr_1",
            "text": "记得喝水",
            "agent_name": "助手",
        }
