"""tests/integration/test_cron_api.py — cron CRUD + run-now + trigger validation.

Plan §12.6 mandates this file. Covers list/create/get/patch/delete cycle,
trigger validation surfacing CRON_TRIGGER_INVALID at create + patch, and
run-now invoking the cron manager and updating last_status.
"""

from __future__ import annotations

import json
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


async def test_cron_cannot_rebind_or_reset_another_users_session(env: Any) -> None:
    client, server, owner_auth, peer_auth, agent_id = env
    base = f"/api/agents/{agent_id}"
    response = await client.patch(base, headers=owner_auth, json={"is_shared": True})
    assert response.status_code == 200, response.text

    owner_thread = (await client.post(f"{base}/threads", headers=owner_auth)).json()
    peer_thread = (await client.post(f"{base}/threads", headers=peer_auth)).json()
    response = await client.post(
        f"{base}/cron",
        headers=owner_auth,
        json={
            "trigger": "interval:3600",
            "prompt": "ping",
            "enabled": False,
            "session_key": peer_thread["session_key"],
        },
    )
    assert response.status_code == 403, response.text

    job = (
        await client.post(
            f"{base}/cron",
            headers=owner_auth,
            json={"trigger": "interval:3600", "prompt": "ping", "enabled": False},
        )
    ).json()
    cron_path = f"{base}/cron/{job['id']}"

    response = await client.patch(
        cron_path,
        headers=owner_auth,
        json={"session_key": peer_thread["session_key"], "fresh_thread": True},
    )
    assert response.status_code == 403, response.text
    assert (await client.get(cron_path, headers=owner_auth)).json()["session_key"] == owner_thread[
        "session_key"
    ]

    # Old rows can already contain a foreign session binding, so delivery must check too.
    server.services.repos.cron_repo.update(
        job["id"], session_key=peer_thread["session_key"], fresh_thread=True
    )
    with pytest.raises(ValueError, match="does not belong to user"):
        await server.app_runtime.cron_manager.run_now(job["id"], wait=True)

    threads = (await client.get(f"{base}/threads", headers=peer_auth)).json()
    assert next(t["thread_id"] for t in threads if t["is_active"]) == peer_thread["thread_id"]


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


async def test_cron_examples_missing_field_uses_name_defaults(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.get(f"/api/agents/{aid}/cron/examples", headers=alice_auth)
    assert r.status_code == 200, r.text
    examples = r.json()["task_examples"]
    assert examples is not None
    assert len(examples["zh"]) == 6
    assert "bot" in examples["zh"][0]
    assert len(examples["en"]) == 6
    assert "bot" in examples["en"][0]


async def test_cron_examples_reads_workspace_manifest(env: Any) -> None:
    c, srv, alice_auth, bob_auth, aid = env
    workspace = srv.app_runtime.agent_registry.workspace_for_agent(aid)
    assert workspace is not None
    await workspace.awrite_text(
        ".octop/manifest.json",
        json.dumps(
            {
                "id": "demo",
                "task_examples": {
                    "zh": ["每天 09:00 巡检"],
                    "en": ["Patrol daily at 09:00"],
                },
            }
        ),
        force=True,
    )
    r = await c.get(f"/api/agents/{aid}/cron/examples", headers=alice_auth)
    assert r.status_code == 200, r.text
    assert r.json()["task_examples"] == {
        "zh": ["每天 09:00 巡检"],
        "en": ["Patrol daily at 09:00"],
    }
    denied = await c.get(f"/api/agents/{aid}/cron/examples", headers=bob_auth)
    assert denied.status_code == 403


async def test_cron_examples_display_normalizes_four_or_five_to_three(env: Any) -> None:
    c, srv, alice_auth, _bob_auth, aid = env
    workspace = srv.app_runtime.agent_registry.workspace_for_agent(aid)
    assert workspace is not None
    await workspace.awrite_text(
        ".octop/manifest.json",
        json.dumps(
            {
                "id": "demo",
                "task_examples": {
                    "zh": ["一", "二", "三", "四", "五"],
                    "en": ["a", "b", "c", "d", "e"],
                },
            }
        ),
        force=True,
    )
    r = await c.get(f"/api/agents/{aid}/cron/examples", headers=alice_auth)
    assert r.status_code == 200, r.text
    assert r.json()["task_examples"] == {"zh": ["一", "二", "三"], "en": ["a", "b", "c"]}
    welcome = await c.get(f"/api/agents/{aid}/chat/welcome", headers=alice_auth)
    assert welcome.status_code == 200, welcome.text
    assert welcome.json()["task_examples"] == {"zh": ["一", "二", "三"], "en": ["a", "b", "c"]}


async def test_settings_timezone_returns_default(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, _aid = env
    r = await c.get("/api/settings/timezone", headers=alice_auth)
    assert r.status_code == 200
    assert r.json() == {"timezone": "Asia/Shanghai"}


async def test_settings_upload_returns_default_limit(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, _aid = env
    r = await c.get("/api/settings/upload", headers=alice_auth)
    assert r.status_code == 200
    assert r.json() == {"max_upload_mb": 100, "max_upload_bytes": 100 * 1024 * 1024}


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
