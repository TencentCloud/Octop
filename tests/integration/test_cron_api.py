"""tests/integration/test_cron_api.py — cron CRUD + run-now + trigger validation.

Plan §12.6 mandates this file. Covers list/create/get/patch/delete cycle,
trigger validation surfacing CRON_TRIGGER_INVALID at create + patch, and
run-now invoking the cron manager and updating last_status.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
async def env(env_alice_bob_agent):
    yield env_alice_bob_agent


# --- CRUD cycle ---------------------------------------------------------------


async def test_create_lists_get_patch_delete_cycle(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env

    # CREATE with valid interval trigger
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={
            "trigger": "interval:60",
            "prompt": "ping the server",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    cid = body["id"]
    assert body["trigger"] == "interval:60"
    assert body["prompt"] == "ping the server"
    assert body["fresh_thread"] is False
    assert body["enabled"] is True
    assert body["last_status"] is None

    # LIST contains the row
    r = await c.get(f"/api/agents/{aid}/cron", headers=alice_auth)
    assert r.status_code == 200
    rows = r.json()
    assert any(row["id"] == cid for row in rows)

    # GET single
    r = await c.get(f"/api/agents/{aid}/cron/{cid}", headers=alice_auth)
    assert r.status_code == 200
    assert r.json()["id"] == cid

    # PATCH prompt + enabled
    r = await c.patch(
        f"/api/agents/{aid}/cron/{cid}",
        headers=alice_auth,
        json={"prompt": "ping-v2", "enabled": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["prompt"] == "ping-v2"
    assert body["enabled"] is False

    # DELETE → 204
    r = await c.delete(f"/api/agents/{aid}/cron/{cid}", headers=alice_auth)
    assert r.status_code == 204

    # GET after delete → 404
    r = await c.get(f"/api/agents/{aid}/cron/{cid}", headers=alice_auth)
    assert r.status_code == 404


# --- Trigger validation -------------------------------------------------------


async def test_create_with_invalid_trigger_returns_400(env: Any) -> None:
    """Plan §12.6: ``build_trigger`` is called server-side at create;
    invalid spec must surface ``CRON_TRIGGER_INVALID`` (HTTP 400)."""
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={
            "trigger": "not-a-valid-trigger",  # missing kind:value
            "prompt": "noop",
        },
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CRON_TRIGGER_INVALID"


async def test_create_with_invalid_cron_expr_returns_400(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={
            "trigger": "cron:not a real cron",
            "prompt": "noop",
        },
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CRON_TRIGGER_INVALID"


async def test_patch_invalid_trigger_returns_400(env: Any) -> None:
    """Validation also runs on PATCH when trigger is updated."""
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={"trigger": "interval:30", "prompt": "x"},
    )
    cid = r.json()["id"]

    r = await c.patch(
        f"/api/agents/{aid}/cron/{cid}",
        headers=alice_auth,
        json={"trigger": "garbage"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CRON_TRIGGER_INVALID"


async def test_create_with_valid_cron_expr(env: Any) -> None:
    """`cron:* * * * *` should pass validation."""
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={
            "trigger": "cron:* * * * *",
            "prompt": "tick",
        },
    )
    assert r.status_code == 201, r.text


# --- Run-now ------------------------------------------------------------------


async def test_run_now_records_last_status(env: Any) -> None:
    """Run-now should invoke the cron manager and the job's repo update
    leaves ``last_status`` set."""
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={
            "trigger": "interval:3600",
            "prompt": "do the thing",
        },
    )
    cid = r.json()["id"]

    r = await c.post(f"/api/agents/{aid}/cron/{cid}/run-now", headers=alice_auth)
    assert r.status_code == 204

    r = await c.get(f"/api/agents/{aid}/cron/{cid}", headers=alice_auth)
    assert r.status_code == 200
    body = r.json()
    # CronJob.run() writes a status string ("ok" / "error" / etc.) — assert
    # the row was touched, regardless of which terminal status it lands on.
    assert body["last_status"] is not None
    assert body["last_run_at"] is not None


async def test_cron_settings_returns_timezone(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, _aid = env
    r = await c.get("/api/cron/settings", headers=alice_auth)
    assert r.status_code == 200
    assert r.json() == {"timezone": "Asia/Shanghai"}


async def test_settings_timezone_returns_default(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, _aid = env
    r = await c.get("/api/settings/timezone", headers=alice_auth)
    assert r.status_code == 200
    assert r.json() == {"timezone": "Asia/Shanghai"}


async def test_run_now_unknown_cron_returns_404(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron/01HMISSING0000000000000000/run-now",
        headers=alice_auth,
    )
    assert r.status_code == 404


# --- Cross-user isolation -----------------------------------------------------


async def test_cross_user_cannot_list_cron(env: Any) -> None:
    c, _srv, _alice_auth, bob_auth, aid = env
    r = await c.get(f"/api/agents/{aid}/cron", headers=bob_auth)
    assert r.status_code == 403
