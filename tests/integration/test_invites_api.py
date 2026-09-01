"""Integration tests for one-time user invites."""

from __future__ import annotations

import json

from octop.infra.agents.default_agent import default_home_local_backend
from octop.infra.utils.host_dirs import host_home_dir, host_path_text


async def test_invite_create_list_redeem_and_one_time(env) -> None:
    c, srv, auth = env

    r = await c.post(
        "/api/users/invites",
        headers=auth,
        json={"note": "for bob", "expires_in_days": 7},
    )
    assert r.status_code == 201, r.text
    invite = r.json()
    assert invite["status"] == "pending"
    assert invite["note"] == "for bob"
    assert invite["code"]
    assert invite["invite_path"].startswith("/invite?code=")
    assert invite["invite_url"].endswith(invite["invite_path"])
    code = invite["code"]

    listed = await c.get("/api/users/invites", headers=auth)
    assert listed.status_code == 200
    assert any(row["code"] == code for row in listed.json())

    # Public validate — no auth
    v = await c.post("/api/auth/invite/validate", json={"code": code})
    assert v.status_code == 200
    assert v.json()["ok"] is True

    redeem = await c.post(
        "/api/auth/invite/redeem",
        json={
            "code": code,
            "username": "bob_invitee",
            "password": "InvitePass12",
            "display_name": "Bob",
        },
    )
    assert redeem.status_code == 200, redeem.text
    body = redeem.json()
    assert body["access_token"]
    assert body["user"]["username"] == "bob_invitee"
    assert body["user"]["role"] == "user"
    assert body["user"]["permissions"] == []

    me = await c.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == "bob_invitee"

    # Same default expert as setup wizard (general-assistant), not pinned to ``main``.
    agents = await c.get(
        "/api/agents",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert agents.status_code == 200, agents.text
    bob_agents = agents.json()
    assert len(bob_agents) == 1
    assert bob_agents[0]["template_name"] == "general-assistant"
    assert bob_agents[0]["agent_id"] != "main"
    assert srv.app_runtime is not None
    bob_row = srv.app_runtime.agent_registry.get_row(bob_agents[0]["agent_id"])
    assert bob_row is not None
    bob_cfg = json.loads(bob_row.config_json or "{}")
    assert bob_cfg["backend"] == default_home_local_backend()
    assert bob_cfg["backend"]["root_dir"] == host_path_text(host_home_dir())
    assert bob_cfg["workspace_dir"] == f"/.octop/workspaces/{bob_agents[0]['agent_id']}"

    again = await c.post(
        "/api/auth/invite/redeem",
        json={
            "code": code,
            "username": "other_user",
            "password": "InvitePass12",
        },
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "INVITE_USED"

    listed2 = await c.get("/api/users/invites", headers=auth)
    row = next(x for x in listed2.json() if x["code"] == code)
    assert row["status"] == "used"


async def test_invite_revoke(env) -> None:
    c, _srv, auth = env
    created = await c.post("/api/users/invites", headers=auth, json={})
    assert created.status_code == 201
    invite_id = created.json()["id"]
    code = created.json()["code"]

    revoked = await c.post(f"/api/users/invites/{invite_id}/revoke", headers=auth)
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    v = await c.post("/api/auth/invite/validate", json={"code": code})
    assert v.status_code == 410
    assert v.json()["error"]["code"] == "INVITE_REVOKED"


async def test_invite_admin_requires_users_permission(env) -> None:
    c, _srv, auth = env
    r = await c.post(
        "/api/users",
        headers=auth,
        json={"username": "normie", "password": "TestPass12", "role": "user"},
    )
    assert r.status_code == 201
    tok = (
        await c.post(
            "/api/auth/login",
            json={"username": "normie", "password": "TestPass12"},
        )
    ).json()["access_token"]
    denied = await c.get(
        "/api/users/invites",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert denied.status_code == 403
