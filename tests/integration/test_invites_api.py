"""Integration tests for reusable user invites."""

from __future__ import annotations

import json

from octop.infra.agents.experts.default_agent import default_home_local_backend
from octop.infra.utils.host_dirs import host_fs_tree_root


async def test_invite_create_list_redeem_multiple(env) -> None:
    c, srv, auth = env

    r = await c.post(
        "/api/users/invites",
        headers=auth,
        json={"note": "for bob", "expires_in_days": 7, "max_uses": 2},
    )
    assert r.status_code == 201, r.text
    invite = r.json()
    assert invite["status"] == "active"
    assert invite["max_uses"] == 2
    assert invite["use_count"] == 0
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
    assert bob_cfg["backend"]["root_dir"] == host_fs_tree_root()
    assert bob_cfg["workspace_dir"] == str(
        srv.paths.agent_workspace(bob_agents[0]["agent_id"]).resolve()
    )

    again = await c.post(
        "/api/auth/invite/redeem",
        json={
            "code": code,
            "username": "other_user",
            "password": "InvitePass12",
        },
    )
    assert again.status_code == 200, again.text
    users = await c.get(f"/api/users/invites/{invite['id']}/users?page_size=1", headers=auth)
    assert users.status_code == 200
    assert users.json()["total"] == 2
    assert len(users.json()["users"]) == 1
    users_page2 = await c.get(
        f"/api/users/invites/{invite['id']}/users?page=2&page_size=1", headers=auth
    )
    assert {users.json()["users"][0]["username"], users_page2.json()["users"][0]["username"]} == {
        "bob_invitee",
        "other_user",
    }

    listed2 = await c.get("/api/users/invites", headers=auth)
    row = next(x for x in listed2.json() if x["code"] == code)
    assert row["status"] == "disabled"
    assert row["enabled"] is False
    assert row["use_count"] == 2
    assert row["max_uses"] == 2

    full = await c.patch(f"/api/users/invites/{invite['id']}", headers=auth, json={"enabled": True})
    assert full.status_code == 409
    assert full.json()["error"]["code"] == "INVITE_EXHAUSTED"
    blocked = await c.post(
        "/api/auth/invite/redeem",
        json={"code": code, "username": "over_quota", "password": "InvitePass12"},
    )
    assert blocked.status_code == 410
    assert blocked.json()["error"]["code"] == "INVITE_DISABLED"


async def test_invite_revoke(env) -> None:
    c, _srv, auth = env
    created = await c.post("/api/users/invites", headers=auth, json={})
    assert created.status_code == 201
    assert created.json()["max_uses"] == 1
    invite_id = created.json()["id"]
    code = created.json()["code"]

    revoked = await c.post(f"/api/users/invites/{invite_id}/revoke", headers=auth)
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "disabled"

    v = await c.post("/api/auth/invite/validate", json={"code": code})
    assert v.status_code == 410
    assert v.json()["error"]["code"] == "INVITE_DISABLED"
    blocked = await c.post(
        "/api/auth/invite/redeem",
        json={"code": code, "username": "blocked", "password": "InvitePass12"},
    )
    assert blocked.json()["error"]["code"] == "INVITE_DISABLED"
    enabled = await c.patch(f"/api/users/invites/{invite_id}", headers=auth, json={"enabled": True})
    assert enabled.status_code == 200 and enabled.json()["status"] == "active"
    assert (await c.post("/api/auth/invite/validate", json={"code": code})).status_code == 200


async def test_invite_rejects_invalid_registration_limit(env) -> None:
    c, _srv, auth = env
    for max_uses in (0, -1, 1.5, True, None, 2_147_483_648):
        response = await c.post("/api/users/invites", headers=auth, json={"max_uses": max_uses})
        assert response.status_code == 422, response.text


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
    denied_users = await c.get(
        "/api/users/invites/1/users", headers={"Authorization": f"Bearer {tok}"}
    )
    assert denied_users.status_code == 403
    denied_update = await c.patch(
        "/api/users/invites/1",
        headers={"Authorization": f"Bearer {tok}"},
        json={"enabled": False},
    )
    assert denied_update.status_code == 403


async def test_expired_invite_rejects_validate_and_registration(env) -> None:
    c, srv, auth = env
    created = (await c.post("/api/users/invites", headers=auth, json={})).json()
    with srv.services.db.transaction() as conn:
        conn.execute("UPDATE user_invites SET expires_at = 0 WHERE id = ?", (created["id"],))
    validate = await c.post("/api/auth/invite/validate", json={"code": created["code"]})
    assert validate.json()["error"]["code"] == "INVITE_EXPIRED"
    redeem = await c.post(
        "/api/auth/invite/redeem",
        json={"code": created["code"], "username": "expired_user", "password": "InvitePass12"},
    )
    assert redeem.json()["error"]["code"] == "INVITE_EXPIRED"
