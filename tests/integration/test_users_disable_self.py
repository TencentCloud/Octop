"""tests/integration/test_users_disable_self.py"""

from __future__ import annotations


async def test_admin_cannot_disable_self(env):
    c, _srv, auth = env
    me = (await c.get("/api/auth/me", headers=auth)).json()

    r = await c.patch(f"/api/users/{me['id']}", headers=auth, json={"disabled": True})

    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "FORBIDDEN"


async def test_self_disable_guard_keeps_admin_session_usable(env):
    """The rejected PATCH must leave the actor's own account active."""
    c, _srv, auth = env
    me = (await c.get("/api/auth/me", headers=auth)).json()

    assert (
        await c.patch(f"/api/users/{me['id']}", headers=auth, json={"disabled": True})
    ).status_code == 403

    still_me = await c.get("/api/auth/me", headers=auth)
    assert still_me.status_code == 200, still_me.text
    row = await c.get(f"/api/users/{me['id']}", headers=auth)
    assert row.status_code == 200, row.text
    assert row.json()["disabled"] is False


async def test_self_disable_guard_rejects_whole_patch(env):
    """Self-disable is refused before any field of the same patch is written."""
    c, _srv, auth = env
    me = (await c.get("/api/auth/me", headers=auth)).json()
    original_name = me["display_name"]

    r = await c.patch(
        f"/api/users/{me['id']}",
        headers=auth,
        json={"disabled": True, "display_name": "locked out"},
    )

    assert r.status_code == 403, r.text
    row = await c.get(f"/api/users/{me['id']}", headers=auth)
    assert row.json()["disabled"] is False
    assert row.json()["display_name"] == original_name


async def test_admin_can_disable_other_user(env):
    """The guard covers the actor only — disabling anyone else still works."""
    c, _srv, auth = env
    created = await c.post(
        "/api/users",
        headers=auth,
        json={"username": "carol", "password": "TestPass12", "role": "user"},
    )
    assert created.status_code == 201, created.text
    uid = created.json()["id"]

    r = await c.patch(f"/api/users/{uid}", headers=auth, json={"disabled": True})

    assert r.status_code == 200, r.text
    assert r.json()["disabled"] is True
