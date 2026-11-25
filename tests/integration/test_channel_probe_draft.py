"""Integration tests for draft channel config probe."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
async def env(env_alice_bob_agent):
    yield env_alice_bob_agent


@pytest.mark.parametrize(
    "kind,config",
    [("qq", {"app_id": "1", "client_secret": "sec"}), ("discord", {"bot_token": "fake"})],
)
async def test_probe_draft_config(env: Any, kind: str, config: dict) -> None:
    c, srv, alice_auth, _bob_auth, aid = env
    with patch.object(
        srv.app_runtime.gateway,
        "probe_config",
        new=AsyncMock(return_value={"ok": True}),
    ) as probe:
        r = await c.post(
            f"/api/agents/{aid}/channels/probe",
            headers=alice_auth,
            json={"kind": kind, "config": config},
        )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    probe.assert_awaited_once()


async def test_probe_reuses_stored_secret(env: Any) -> None:
    c, srv, alice_auth, _bob_auth, aid = env
    created = await c.post(
        f"/api/agents/{aid}/channels",
        headers=alice_auth,
        json={"kind": "discord", "name": "main", "config": {"bot_token": "stored-token"}},
    )
    assert created.status_code == 201, created.text
    channel_id = created.json()["id"]
    with patch.object(
        srv.app_runtime.gateway,
        "probe_config",
        new=AsyncMock(return_value={"ok": True}),
    ) as probe:
        response = await c.post(
            f"/api/agents/{aid}/channels/probe",
            headers=alice_auth,
            json={
                "kind": "discord",
                "channel_id": channel_id,
                "config": {"allow_all_channels": True},
            },
        )
    assert response.status_code == 200, response.text
    assert "stored-token" not in response.text
    assert probe.await_args.kwargs["config"]["bot_token"] == "stored-token"
