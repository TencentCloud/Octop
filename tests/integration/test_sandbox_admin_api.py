"""tests/integration/test_sandbox_admin_api.py — /api/admin/sandboxes routes."""

from __future__ import annotations

from typing import Any

from octop.infra.backend.sandbox_admin import LABEL_SANDBOX, LABEL_SCOPE


def _fake_container(name: str, image: str, networks: dict[str, Any]) -> Any:
    class _C:
        name = name
        id = "abcdef123456"
        attrs = {
            "Config": {
                "Image": image,
                "Labels": {LABEL_SANDBOX: "1", LABEL_SCOPE: "agent"},
                "WorkingDir": "/workspace/a1",
            },
            "State": {"Status": "running"},
            "Created": "2026-10-23T00:00:00",
            "NetworkSettings": {"Networks": networks},
        }

    return _C()


async def test_sandboxes_requires_admin_permission(env) -> None:
    c, _srv, admin_auth = env
    r = await c.get("/api/admin/sandboxes", headers=admin_auth)
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        assert isinstance(r.json(), list)


async def test_sandboxes_forbidden_for_regular_user(env) -> None:
    c, _srv, admin_auth = env
    await c.post(
        "/api/users",
        headers=admin_auth,
        json={"username": "plain", "password": "TestPass12", "role": "user"},
    )
    tok = (
        await c.post("/api/auth/login", json={"username": "plain", "password": "TestPass12"})
    ).json()["access_token"]
    r = await c.get("/api/admin/sandboxes", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


async def test_recreate_unknown_container_404(env) -> None:
    c, _srv, auth = env
    r = await c.post("/api/admin/sandboxes/nope/recreate", headers=auth)
    assert r.status_code in (404, 503)
    if r.status_code == 404:
        body = r.json()
        assert body["error"]["code"] == "SANDBOX_CONTAINER_NOT_FOUND"


async def test_backups_of_unknown_container_empty(env) -> None:
    c, _srv, auth = env
    r = await c.get("/api/admin/sandboxes/backups/nope", headers=auth)
    assert r.status_code == 200
    assert r.json() == []
