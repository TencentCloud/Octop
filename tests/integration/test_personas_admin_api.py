"""tests/integration/test_personas_admin_api.py — MBTI preview + admin routers.

Covers:
- ``GET /api/mbti/types`` returns 16 MBTI profiles.
- ``GET /api/mbti/preview/{code}`` renders preview with the current user.
- ``GET /api/admin/overview`` includes users + agents + totals.
- ``GET /api/admin/audit-log`` returns rows; filters honored.
- ``GET /api/admin/metrics`` returns counter snapshot.
- Non-admin gets 403 on every admin endpoint.
"""

from __future__ import annotations

from typing import Any

import pytest

from octop.api.routers.admin import AUDIT_LOG_MAX_LIMIT
from tests.support.auth import create_agent


@pytest.fixture
async def env(env_admin_alice):
    client, srv, admin_auth, alice_auth = env_admin_alice
    await create_agent(
        client,
        admin_auth,
        name="alices-bot",
        config={"providers": ["openai"], "default_model": "openai:gpt-4o"},
    )
    yield client, srv, admin_auth, alice_auth


# --- MBTI preview -------------------------------------------------------------


async def test_list_mbti_types_returns_16_entries(env: Any) -> None:
    c, _srv, _admin_auth, alice_auth = env
    r = await c.get("/api/mbti/types", headers=alice_auth)
    assert r.status_code == 200
    rows = r.json()
    codes = [row["code"] for row in rows]
    assert len(codes) == 16
    for c4 in ("INTJ", "ENFP", "ISTJ", "ESFP"):
        assert c4 in codes


async def test_get_persona_preview_substitutes_user(env: Any) -> None:
    c, _srv, _admin_auth, alice_auth = env
    r = await c.get("/api/mbti/preview/INTJ", headers=alice_auth)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "INTJ"
    assert isinstance(body["preview"], str)
    assert body["preview"]
    assert "alice" in body["preview"].lower()


async def test_get_persona_default_returns_preview(env: Any) -> None:
    c, _srv, _admin_auth, alice_auth = env
    r = await c.get("/api/mbti/preview/_default", headers=alice_auth)
    assert r.status_code == 200
    assert r.json()["preview"]


# --- Admin overview -----------------------------------------------------------


async def test_admin_overview_lists_users_and_agents(env: Any) -> None:
    c, _srv, admin_auth, _alice_auth = env
    r = await c.get("/api/admin/overview", headers=admin_auth)
    assert r.status_code == 200
    body = r.json()

    usernames = {u["username"] for u in body["users"]}
    assert {"admin", "alice"}.issubset(usernames)

    # In the global agent architecture, agents are in body["agents"]
    # not nested under each user.
    assert "agents" in body
    assert any(a["name"] == "alices-bot" for a in body["agents"])

    totals = body["totals"]
    assert totals["users"] >= 2
    assert totals["agents"] >= 1


async def test_admin_overview_non_admin_403(env: Any) -> None:
    c, _srv, _admin_auth, alice_auth = env
    r = await c.get("/api/admin/overview", headers=alice_auth)
    assert r.status_code == 403


# --- Admin audit log ----------------------------------------------------------


async def test_admin_audit_log_returns_list(env: Any) -> None:
    """Audit log endpoint must respond 200 with a list (may be empty)."""
    c, _srv, admin_auth, _alice_auth = env
    r = await c.get("/api/admin/audit-log", headers=admin_auth)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_admin_audit_log_honors_limit(env: Any) -> None:
    c, _srv, admin_auth, _alice_auth = env
    r = await c.get("/api/admin/audit-log?limit=5", headers=admin_auth)
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) <= 5


async def test_admin_audit_log_rejects_limit_out_of_bounds(env: Any) -> None:
    """A non-positive ``limit`` must not reach SQL ``LIMIT``.

    SQLite reads a negative LIMIT as "no limit at all" (the whole audit log in one
    response) and ``LIMIT 0`` as "no rows"; the thread list got the same bound.
    """
    c, _srv, admin_auth, _alice_auth = env
    for bad in (0, -1, AUDIT_LOG_MAX_LIMIT + 1):
        r = await c.get(f"/api/admin/audit-log?limit={bad}", headers=admin_auth)
        assert r.status_code == 422, f"limit={bad} -> {r.status_code}: {r.text}"


async def test_admin_audit_log_accepts_the_largest_panel_page(env: Any) -> None:
    c, _srv, admin_auth, _alice_auth = env
    r = await c.get(f"/api/admin/audit-log?limit={AUDIT_LOG_MAX_LIMIT}", headers=admin_auth)
    assert r.status_code == 200, r.text


async def test_admin_audit_log_non_admin_403(env: Any) -> None:
    c, _srv, _admin_auth, alice_auth = env
    r = await c.get("/api/admin/audit-log", headers=alice_auth)
    assert r.status_code == 403


# --- Admin metrics ------------------------------------------------------------


async def test_admin_metrics_returns_dict(env: Any) -> None:
    c, _srv, admin_auth, _alice_auth = env
    r = await c.get("/api/admin/metrics", headers=admin_auth)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    # `agent_active` is set inside the handler from the snapshot — alice's
    # autostarted agent should make it >= 1, but we don't assert exact
    # values: the contract is "a counter snapshot dict comes back".
    assert "agent_active" in body


async def test_admin_metrics_non_admin_403(env: Any) -> None:
    c, _srv, _admin_auth, alice_auth = env
    r = await c.get("/api/admin/metrics", headers=alice_auth)
    assert r.status_code == 403
