"""Integration tests for /api/envs."""

from __future__ import annotations

from typing import Any


async def test_envs_crud_cycle(env: Any) -> None:
    c, srv, auth = env
    r = await c.get("/api/envs", headers=auth)
    assert r.status_code == 200
    assert r.json() == []

    r = await c.put("/api/envs", headers=auth, json={"TAVILY_API_KEY": "tvly-1", "FOO": "bar"})
    assert r.status_code == 200
    body = r.json()
    assert {row["key"] for row in body} == {"FOO", "TAVILY_API_KEY"}

    env_path = srv.paths.root / "env"
    assert env_path.is_file()
    assert "TAVILY_API_KEY" in env_path.read_text(encoding="utf-8")

    r = await c.delete("/api/envs/FOO", headers=auth)
    assert r.status_code == 200
    assert {row["key"] for row in r.json()} == {"TAVILY_API_KEY"}


async def test_envs_put_unsets_removed_process_keys(env: Any) -> None:
    import os

    c, _srv, auth = env
    r = await c.put("/api/envs", headers=auth, json={"GONE": "1", "KEEP": "2"})
    assert r.status_code == 200
    assert os.environ.get("GONE") == "1"
    r = await c.put("/api/envs", headers=auth, json={"KEEP": "2"})
    assert r.status_code == 200
    assert "GONE" not in os.environ
    assert os.environ.get("KEEP") == "2"


async def test_envs_non_admin_forbidden(env: Any) -> None:
    c, _srv, admin_auth = env
    await c.post(
        "/api/users",
        headers=admin_auth,
        json={"username": "bob", "password": "TestPass12", "role": "user"},
    )
    bob_tok = (
        await c.post("/api/auth/login", json={"username": "bob", "password": "TestPass12"})
    ).json()["access_token"]
    r = await c.get("/api/envs", headers={"Authorization": f"Bearer {bob_tok}"})
    assert r.status_code == 403
