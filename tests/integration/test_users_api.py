"""tests/integration/test_users_api.py"""

from __future__ import annotations


async def test_create_list_get_delete(env):
    c, srv, auth = env
    r = await c.post(
        "/api/users",
        headers=auth,
        json={"username": "alice", "password": "TestPass12", "role": "user"},
    )
    assert r.status_code == 201
    uid = r.json()["id"]

    r = await c.get("/api/users", headers=auth)
    usernames = [u["username"] for u in r.json()]
    assert "alice" in usernames

    r = await c.get(f"/api/users/{uid}", headers=auth)
    assert r.json()["username"] == "alice"
    assert r.json()["login_locked"] is False
    assert r.json()["login_retry_after_seconds"] == 0
    assert isinstance(r.json()["created_at"], int)
    assert r.json()["created_at"] > 0

    r = await c.delete(f"/api/users/{uid}", headers=auth)
    assert r.status_code == 204
    r = await c.get(f"/api/users/{uid}", headers=auth)
    assert r.status_code == 404


async def test_non_admin_gets_403(env):
    c, srv, _ = env
    admin_auth = env[2]
    await c.post(
        "/api/users",
        headers=admin_auth,
        json={"username": "bob", "password": "TestPass12", "role": "user"},
    )
    tok = (
        await c.post("/api/auth/login", json={"username": "bob", "password": "TestPass12"})
    ).json()["access_token"]
    user_auth = {"Authorization": f"Bearer {tok}"}
    r = await c.get("/api/users", headers=user_auth)
    assert r.status_code == 403


async def test_admin_cannot_delete_self(env):
    c, srv, auth = env
    me = (await c.get("/api/auth/me", headers=auth)).json()
    r = await c.delete(f"/api/users/{me['id']}", headers=auth)
    assert r.status_code == 403


async def test_admin_cannot_demote_self(env):
    c, srv, auth = env
    me = (await c.get("/api/auth/me", headers=auth)).json()
    r = await c.patch(f"/api/users/{me['id']}", headers=auth, json={"role": "user"})
    assert r.status_code == 403


async def test_admin_can_enable_disabled_user(env):
    c, srv, auth = env
    r = await c.post(
        "/api/users",
        headers=auth,
        json={"username": "disabled_user", "password": "TestPass12", "role": "user"},
    )
    assert r.status_code == 201
    uid = r.json()["id"]

    r = await c.patch(f"/api/users/{uid}", headers=auth, json={"disabled": True})
    assert r.status_code == 200
    assert r.json()["disabled"] is True

    r = await c.patch(f"/api/users/{uid}", headers=auth, json={"disabled": False})
    assert r.status_code == 200
    assert r.json()["disabled"] is False


async def test_admin_can_unlock_login(env):
    c, srv, auth = env
    r = await c.post(
        "/api/users",
        headers=auth,
        json={"username": "lock_user", "password": "TestPass12", "role": "user"},
    )
    uid = r.json()["id"]
    max_attempts = srv.services.config.login_max_attempts
    for _ in range(max_attempts):
        await c.post("/api/auth/login", json={"username": "lock_user", "password": "bad"})
    r = await c.get(f"/api/users/{uid}", headers=auth)
    assert r.json()["login_locked"] is True

    r = await c.post(f"/api/users/{uid}/unlock-login", headers=auth)
    assert r.status_code == 204
    r = await c.get(f"/api/users/{uid}", headers=auth)
    assert r.json()["login_locked"] is False

    r = await c.post("/api/auth/login", json={"username": "lock_user", "password": "TestPass12"})
    assert r.status_code == 200
