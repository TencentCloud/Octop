"""tests/integration/test_agents_prefs_api.py — schema v21 pin/order endpoints."""

from __future__ import annotations

import pytest

from tests.support.auth import create_user


@pytest.fixture
async def env(env_with_provider):
    yield env_with_provider


async def _mk_agent(client, auth, name: str) -> str:
    r = await client.post("/api/agents", headers=auth, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["agent_id"]


async def test_list_carries_pinned_and_sort_order_defaults(env) -> None:
    client, _, auth = env
    agent_id = await _mk_agent(client, auth, "pref-defaults")
    listed = await client.get("/api/agents", headers=auth)
    assert listed.status_code == 200
    row = next(a for a in listed.json() if a["agent_id"] == agent_id)
    assert row["pinned"] is False
    assert row["sort_order"] == -1


async def test_pin_and_reorder_roundtrip(env) -> None:
    client, _, auth = env
    a = await _mk_agent(client, auth, "order-a")
    b = await _mk_agent(client, auth, "order-b")
    c = await _mk_agent(client, auth, "order-c")

    r = await client.put(
        "/api/agents/order", headers=auth, json={"order": [c, a, b]}
    )
    assert r.status_code == 204, r.text

    r = await client.post(
        f"/api/agents/{b}/pin", headers=auth, json={"pinned": True}
    )
    assert r.status_code == 204, r.text

    listed = await client.get("/api/agents", headers=auth)
    order = [row["agent_id"] for row in listed.json() if row["agent_id"] in {a, b, c}]
    # pinned b first, then manual sequence c, a (b already placed in pinned)
    assert order == [b, c, a]

    row = next(x for x in listed.json() if x["agent_id"] == b)
    assert row["pinned"] is True

    r = await client.post(f"/api/agents/{b}/pin", headers=auth, json={"pinned": False})
    assert r.status_code == 204
    listed = await client.get("/api/agents", headers=auth)
    order = [row["agent_id"] for row in listed.json() if row["agent_id"] in {a, b, c}]
    assert order == [c, a, b]  # unpinned, falls back into manual sequence


async def test_order_rejects_foreign_private_agent(env) -> None:
    """Ordering someone else's private agent is a privilege leak → 4xx.

    Uses a regular (non-admin) user: admins are globally visible by design,
    so only a normal user can demonstrate the denial.
    """
    client, _, admin_auth = env
    victim_auth = await create_user(client, admin_auth, username="pref_victim")
    attacker_auth = await create_user(client, admin_auth, username="pref_attacker")
    secret = await _mk_agent(client, victim_auth, "victim-secret")

    r = await client.put(
        "/api/agents/order", headers=attacker_auth, json={"order": [secret]}
    )
    assert r.status_code == 403, r.text


async def test_order_rejects_unknown_agent(env) -> None:
    client, _, auth = env
    r = await client.put(
        "/api/agents/order", headers=auth, json={"order": ["no-such-agent"]}
    )
    assert r.status_code == 404, r.text


async def test_pin_rejects_unknown_agent(env) -> None:
    client, _, auth = env
    r = await client.post(
        "/api/agents/no-such-agent/pin", headers=auth, json={"pinned": True}
    )
    assert r.status_code == 404, r.text


async def test_order_skips_bridge_shadow_ids(env) -> None:
    """bridge:{cid}:{aid} has no local row — skipped, not rejected."""
    client, _, auth = env
    local = await _mk_agent(client, auth, "bridge-neighbor")
    r = await client.put(
        "/api/agents/order",
        headers=auth,
        json={"order": ["bridge:cid-1:remote-doctor", local]},
    )
    assert r.status_code == 204, r.text
    listed = await client.get("/api/agents", headers=auth)
    row = next(x for x in listed.json() if x["agent_id"] == local)
    assert row["sort_order"] == 0


async def test_shared_agent_order_isolated_between_users(env) -> None:
    """Owner pinning a shared agent must not change the viewer's order."""
    client, _, admin_auth = env
    owner_auth = await create_user(client, admin_auth, username="pref_owner")
    peer_auth = await create_user(client, admin_auth, username="pref_peer")

    shared = await _mk_agent(client, owner_auth, "pref-shared")
    r = await client.patch(
        f"/api/agents/{shared}",
        headers=owner_auth,
        json={"is_shared": True},
    )
    assert r.status_code == 200, r.text

    peer_own = await _mk_agent(client, peer_auth, "peer-own")

    # owner pins the shared agent in their own sidebar
    r = await client.post(
        f"/api/agents/{shared}/pin", headers=owner_auth, json={"pinned": True}
    )
    assert r.status_code == 204, r.text

    owner_list = await client.get("/api/agents", headers=owner_auth)
    owner_order = [row["agent_id"] for row in owner_list.json()]
    assert owner_order.index(shared) == 0  # pinned first for the owner

    # peer has NO prefs of their own yet → falls back to creation order,
    # which puts the (earlier-created) shared agent first. The point: the
    # peer's order is governed by the PEER's prefs, not the owner's pin.
    peer_list = await client.get("/api/agents", headers=peer_auth)
    peer_order = [row["agent_id"] for row in peer_list.json()]
    assert peer_order == [shared, peer_own]

    # peer reorders their own view: own agent first, shared agent last
    r = await client.put(
        "/api/agents/order", headers=peer_auth, json={"order": [peer_own, shared]}
    )
    assert r.status_code == 204, r.text
    peer_list = await client.get("/api/agents", headers=peer_auth)
    assert [row["agent_id"] for row in peer_list.json()] == [peer_own, shared]

    # owner unchanged by the peer's reorder
    owner_list = await client.get("/api/agents", headers=owner_auth)
    assert [row["agent_id"] for row in owner_list.json()][0] == shared


async def test_admin_scope_all_ignores_personal_prefs(env) -> None:
    """scope=all stays in creation order — personal prefs never apply."""
    client, srv, auth = env
    a = await _mk_agent(client, auth, "all-a")
    b = await _mk_agent(client, auth, "all-b")

    r = await client.put("/api/agents/order", headers=auth, json={"order": [b, a]})
    assert r.status_code == 204, r.text
    r = await client.post(f"/api/agents/{b}/pin", headers=auth, json={"pinned": True})
    assert r.status_code == 204, r.text

    listed = await client.get("/api/agents", headers=auth, params={"scope": "all"})
    assert listed.status_code == 200
    order = [row["agent_id"] for row in listed.json() if row["agent_id"] in {a, b}]
    assert order == [a, b]  # creation order, not pin/manual order

    # while scope=mine DOES apply them
    mine = await client.get("/api/agents", headers=auth)
    order = [row["agent_id"] for row in mine.json() if row["agent_id"] in {a, b}]
    assert order == [b, a]


async def test_no_backfill_unchanged_legacy_order(env) -> None:
    """Upgraded installs: users with zero pref rows keep exact pre-upgrade order."""
    client, srv, auth = env
    ids = [await _mk_agent(client, auth, f"legacy-{i}") for i in range(4)]
    listed = await client.get("/api/agents", headers=auth)
    # The bootstrap admin also owns the seeded "main" agent — isolate ours.
    order = [row["agent_id"] for row in listed.json() if row["agent_id"] in set(ids)]
    assert order == ids
    assert all(row["sort_order"] == -1 for row in listed.json())
