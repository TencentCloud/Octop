"""tests/integration/test_auth_flow.py"""

from __future__ import annotations

import pytest

from tests.support.auth import bootstrap_admin


@pytest.fixture
async def client(app_client):
    yield app_client


async def test_setup_required_then_login(client):
    c, srv, home = client
    r = await c.get("/api/setup/status")
    assert r.json()["setup_required"] is True
    r = await c.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert r.status_code == 503 and r.json()["setup_required"] is True
    r = await bootstrap_admin(c, home, username="alice", password="TestPass12")
    assert r.status_code == 201
    r = await c.post("/api/auth/login", json={"username": "alice", "password": "TestPass12"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["username"] == "alice"

    r = await c.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 204


async def test_setup_again_410(client):
    c, _, home = client
    await bootstrap_admin(c, home, username="a", password="TestPass12")
    r = await c.post("/api/setup/initial-admin", json={"username": "b", "password": "TestPass12"})
    assert r.status_code == 410


async def test_change_password(client):
    c, _, home = client
    await bootstrap_admin(c, home, username="a", password="OldPass12")
    tok = (await c.post("/api/auth/login", json={"username": "a", "password": "OldPass12"})).json()[
        "access_token"
    ]
    r = await c.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {tok}"},
        json={"old_password": "OldPass12", "new_password": "NewPass12"},
    )
    assert r.status_code == 204
    assert (
        await c.post("/api/auth/login", json={"username": "a", "password": "OldPass12"})
    ).status_code == 401
    assert (
        await c.post("/api/auth/login", json={"username": "a", "password": "NewPass12"})
    ).status_code == 200


async def test_invalid_token_401(client):
    c, _, home = client
    await bootstrap_admin(c, home, username="a", password="TestPass12")
    r = await c.get("/api/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert r.status_code == 401


async def test_health_no_auth_required(client):
    c, _, _ = client
    r = await c.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body.get("started_at"), int)


async def test_patch_me_updates_display_name(client) -> None:
    c, _srv, home = client
    await bootstrap_admin(c, home)
    tok = (
        await c.post("/api/auth/login", json={"username": "admin", "password": "TestPass12"})
    ).json()["access_token"]
    auth = {"Authorization": f"Bearer {tok}"}

    r = await c.patch("/api/auth/me", json={"display_name": "Alice"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "Alice"
    assert body["username"] == "admin"

    r2 = await c.get("/api/auth/me", headers=auth)
    assert r2.json()["display_name"] == "Alice"


async def test_patch_me_clears_display_name(client) -> None:
    c, _srv, home = client
    await bootstrap_admin(c, home)
    tok = (
        await c.post("/api/auth/login", json={"username": "admin", "password": "TestPass12"})
    ).json()["access_token"]
    auth = {"Authorization": f"Bearer {tok}"}
    await c.patch("/api/auth/me", json={"display_name": "Alice"}, headers=auth)

    r = await c.patch("/api/auth/me", json={"display_name": None}, headers=auth)
    assert r.status_code == 200
    assert r.json()["display_name"] is None


async def test_patch_me_requires_auth(client) -> None:
    c, _srv, home = client
    await bootstrap_admin(c, home)
    r = await c.patch("/api/auth/me", json={"display_name": "Alice"})
    assert r.status_code == 401
