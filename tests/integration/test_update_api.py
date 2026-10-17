"""Integration tests for the mounted service-control surface under /api/update."""

from __future__ import annotations

from typing import Any


async def test_update_status_reports_version_without_channel(env_admin_client: Any) -> None:
    c, auth = env_admin_client
    r = await c.get("/api/update/status", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"current_version", "service_mode", "desktop"}


async def test_update_chain_routes_are_not_mounted(env_admin_client: Any) -> None:
    """Unmounted paths fall through to the SPA catch-all, which is GET-only:
    GET answers 404, other methods answer 405 (`api/app.py` ``spa_fallback``)."""
    c, auth = env_admin_client
    assert (await c.get("/api/update/check", headers=auth)).status_code == 404
    assert (await c.post("/api/update/check", headers=auth)).status_code == 405
    assert (
        await c.patch("/api/update/settings", json={"stable_only": False}, headers=auth)
    ).status_code == 405
    assert (await c.post("/api/update/upgrade", json={}, headers=auth)).status_code == 405
    assert (await c.get("/api/update/progress?task_id=x", headers=auth)).status_code == 404
