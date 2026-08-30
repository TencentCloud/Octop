"""Integration tests for /api/update."""

from __future__ import annotations

from typing import Any


async def test_update_status_shape(env_admin_client: Any) -> None:
    c, auth = env_admin_client
    r = await c.get("/api/update/status", headers=auth)
    assert r.status_code == 200
    body = r.json()
    for key in (
        "current_version",
        "latest_version",
        "has_update",
        "is_editable",
        "service_mode",
        "desktop",
        "error",
        "last_check_time",
        "release_notes",
    ):
        assert key in body


async def test_update_check_admin_only(env_admin_client: Any) -> None:
    c, auth = env_admin_client
    r = await c.post("/api/update/check", headers=auth)
    assert r.status_code == 200
