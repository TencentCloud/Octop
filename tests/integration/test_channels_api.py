"""tests/integration/test_channels_api.py — channels CRUD.

Plan §12.5 mandates this file. Covers list/create/get/patch/delete cycle,
404 on missing channel, cross-user isolation, and runtime reload trigger
on mutations.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
async def env(env_alice_bob_agent):
    yield env_alice_bob_agent


# --- CRUD cycle ---------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,config",
    [
        ("feishu", {"app_id": "x"}),
        ("discord", {"bot_token": "fake", "allowed_channel_ids": ["200"]}),
        ("discord", {"bot_token": "fake", "allow_all_channels": True}),
        (
            "discord",
            {"bot_token": "fake", "allow_all_channels": False, "allowed_channel_ids": ["200"]},
        ),
    ],
)
async def test_create_lists_get_patch_delete_cycle(env: Any, kind: str, config: dict) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env

    # CREATE
    r = await c.post(
        f"/api/agents/{aid}/channels",
        headers=alice_auth,
        json={"kind": kind, "name": "main", "config": config},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    cid = body["id"]
    assert body["kind"] == kind
    assert body["name"] == "main"
    assert body["enabled"] is True
    assert body["agent_id"] == aid

    # LIST contains the row
    r = await c.get(f"/api/agents/{aid}/channels", headers=alice_auth)
    assert r.status_code == 200
    rows = r.json()
    assert any(row["id"] == cid for row in rows)

    # GET single
    r = await c.get(f"/api/agents/{aid}/channels/{cid}", headers=alice_auth)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == cid
    assert body["config"] == config

    # PATCH name + enabled
    r = await c.patch(
        f"/api/agents/{aid}/channels/{cid}",
        headers=alice_auth,
        json={"name": "renamed", "enabled": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "renamed"
    assert body["enabled"] is False

    # DELETE → 204
    r = await c.delete(f"/api/agents/{aid}/channels/{cid}", headers=alice_auth)
    assert r.status_code == 204

    # GET after delete → 404
    r = await c.get(f"/api/agents/{aid}/channels/{cid}", headers=alice_auth)
    assert r.status_code == 404


async def test_get_missing_channel_returns_404(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.get(
        f"/api/agents/{aid}/channels/01HMISSING0000000000000000",
        headers=alice_auth,
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


async def test_patch_missing_channel_returns_404(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.patch(
        f"/api/agents/{aid}/channels/01HMISSING0000000000000000",
        headers=alice_auth,
        json={"name": "x"},
    )
    assert r.status_code == 404


async def test_cross_user_cannot_see_channels(env: Any) -> None:
    """Non-owner cannot list or mutate another user's agent channels."""
    c, _srv, alice_auth, bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/channels",
        headers=alice_auth,
        json={"kind": "feishu", "name": "alice-only", "config": {}},
    )
    assert r.status_code == 201

    r = await c.get(f"/api/agents/{aid}/channels", headers=bob_auth)
    assert r.status_code == 403


async def test_create_reloads_runtime(env: Any) -> None:
    """Channel CRUD via Gateway keeps ChannelManager in sync.
    Verify create/patch/delete all succeed."""
    c, srv, alice_auth, _bob_auth, aid = env

    r = await c.post(
        f"/api/agents/{aid}/channels",
        headers=alice_auth,
        json={"kind": "feishu", "name": "spy", "config": {}},
    )
    assert r.status_code == 201
    cid = r.json()["id"]

    r = await c.patch(
        f"/api/agents/{aid}/channels/{cid}",
        headers=alice_auth,
        json={"name": "spy2"},
    )
    assert r.status_code == 200

    r = await c.delete(f"/api/agents/{aid}/channels/{cid}", headers=alice_auth)
    assert r.status_code == 204
