"""tests/integration/test_admin_providers.py — admin /api/admin/providers CRUD."""

from __future__ import annotations


async def test_admin_create_and_list(env):
    c, _, auth = env
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "shared-gpt", "kind": "openai", "api_key": "sk-test"},
    )
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == "shared-gpt"
    assert "user_id" not in created

    r = await c.get("/api/admin/providers", headers=auth)
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "shared-gpt" in names


async def test_admin_only_admin_can_create(env):
    c, _, admin_auth = env
    await c.post(
        "/api/users",
        headers=admin_auth,
        json={"username": "regular", "password": "TestPass12", "role": "user"},
    )
    tok = (
        await c.post("/api/auth/login", json={"username": "regular", "password": "TestPass12"})
    ).json()["access_token"]
    user_auth = {"Authorization": f"Bearer {tok}"}

    r = await c.post(
        "/api/admin/providers",
        headers=user_auth,
        json={"name": "should-fail", "kind": "openai"},
    )
    assert r.status_code == 403


async def test_admin_delete(env):
    c, _, auth = env
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "to-delete", "kind": "openai"},
    )
    assert r.status_code == 201
    pid = r.json()["id"]

    r = await c.delete(f"/api/admin/providers/{pid}", headers=auth)
    assert r.status_code in (200, 204)

    r = await c.get("/api/admin/providers", headers=auth)
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert pid not in ids
