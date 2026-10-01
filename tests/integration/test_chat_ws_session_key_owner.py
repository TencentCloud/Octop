"""tests/integration/test_chat_ws_session_key_owner.py — a client-supplied
dashboard ``session_key`` must not steer a turn into another user's thread."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from octop.infra.gateway.threads import ThreadRegistry
from tests.support.app import octop_client
from tests.support.auth import (
    auth_header,
    bootstrap_admin,
    create_agent,
    ensure_users,
    resolve_user_id,
    seed_openai_provider,
)
from tests.support.fakes import FakeHarnessAgent
from tests.support.http import chat_ws_path, ws_connect


def _chat_ws(c: httpx.AsyncClient, aid: str, auth: dict[str, str]) -> Any:
    return ws_connect(c._octop_app, chat_ws_path(aid, auth))  # type: ignore[attr-defined]


@pytest.fixture
async def env(tmp_octop_home: Path) -> AsyncIterator[Any]:
    fake = FakeHarnessAgent(
        chunks=[{"type": "token", "node": "agent", "content": "hello"}],
    )
    async with octop_client(tmp_octop_home, fake_agent=fake) as (c, srv):
        await bootstrap_admin(c, tmp_octop_home)
        admin_auth = await auth_header(c)
        await seed_openai_provider(c, admin_auth)
        users = await ensure_users(c, admin_auth, "owner", "peer")
        aid = await create_agent(c, users["owner"])
        shared = await c.patch(
            f"/api/agents/{aid}", headers=users["owner"], json={"is_shared": True}
        )
        assert shared.status_code == 200, shared.text
        owner_uid = await resolve_user_id(c, admin_auth, "owner")
        yield c, srv, aid, users["owner"], users["peer"], owner_uid


async def test_turn_with_another_users_session_key_is_rejected(env: Any) -> None:
    c, srv, aid, owner_auth, peer_auth, owner_uid = env

    async with _chat_ws(c, aid, owner_auth) as ws:
        await ws.send_json({"type": "user_turn", "text": "owner turn"})
        await ws.drain_turn()

    owner_key = ThreadRegistry.dashboard_key(agent_id=aid, user_id=owner_uid)
    owner_thread = srv.app_runtime.gateway.thread_registry.get_bound_thread_id(owner_key)
    assert owner_thread

    async with _chat_ws(c, aid, peer_auth) as ws:
        await ws.send_json({"type": "user_turn", "text": "intruder", "session_key": owner_key})
        frames = await ws.drain_turn()

    assert [f.get("type") for f in frames].count("token") == 0
    assert not any(f.get("thread_id") == owner_thread for f in frames)
    assert srv.app_runtime.gateway.thread_registry.get_bound_thread_id(owner_key) == owner_thread
