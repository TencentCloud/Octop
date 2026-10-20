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
    """Unmounted /api/update paths must never be served.

    The SPA catch-all (`api/app.py` ``spa_fallback``) is only registered when the
    built dashboard exists: with the artifact present, unmatched non-GET paths
    partial-match it and answer 405; without it they are plain 404. CI runs
    ``make test`` before building the frontend, so both statuses are legitimate —
    only the mounted status/restart surface may answer 2xx.
    """
    c, auth = env_admin_client
    assert (await c.get("/api/update/check", headers=auth)).status_code == 404
    assert (await c.post("/api/update/check", headers=auth)).status_code in (404, 405)
    assert (
        await c.patch("/api/update/settings", json={"stable_only": False}, headers=auth)
    ).status_code in (404, 405)
    assert (await c.post("/api/update/upgrade", json={}, headers=auth)).status_code in (
        404,
        405,
    )
    assert (await c.get("/api/update/progress?task_id=x", headers=auth)).status_code == 404
