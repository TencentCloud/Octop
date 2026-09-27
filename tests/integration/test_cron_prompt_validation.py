"""tests/integration/test_cron_prompt_validation.py — cron prompt/name bounds must be 4xx.

``docs/api.md`` documents ``CRON_PROMPT_INVALID`` as the 400 for an empty or
too-long prompt, but no code path raises it: ``require_cron_prompt`` /
``require_cron_name`` raise bare ``ValueError`` inside the create/patch
handlers, so the request reaches the catch-all handler and answers
500 INTERNAL_ERROR instead of a client error.
"""

from __future__ import annotations

from typing import Any

import pytest

from octop.infra.cron.task_type import CRON_NAME_MAX_LEN, CRON_PROMPT_MAX_LEN


@pytest.fixture
async def env(env_alice_bob_agent):
    yield env_alice_bob_agent


# --- POST /api/agents/{id}/cron ------------------------------------------------


async def test_create_with_blank_prompt_returns_400(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={"trigger": "interval:60", "prompt": "   "},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "CRON_PROMPT_INVALID"


async def test_create_with_overlong_prompt_returns_400(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={
            "trigger": "interval:60",
            "prompt": "x" * (CRON_PROMPT_MAX_LEN + 1),
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "CRON_PROMPT_INVALID"


async def test_create_with_overlong_name_returns_400(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={
            "trigger": "interval:60",
            "prompt": "ping",
            "name": "x" * (CRON_NAME_MAX_LEN + 1),
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "CRON_PROMPT_INVALID"


# --- PATCH /api/agents/{id}/cron/{cron_id} -------------------------------------


async def test_patch_with_blank_prompt_returns_400(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={"trigger": "interval:30", "prompt": "x"},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    r = await c.patch(
        f"/api/agents/{aid}/cron/{cid}",
        headers=alice_auth,
        json={"prompt": ""},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "CRON_PROMPT_INVALID"


async def test_patch_with_overlong_name_returns_400(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={"trigger": "interval:30", "prompt": "x"},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    r = await c.patch(
        f"/api/agents/{aid}/cron/{cid}",
        headers=alice_auth,
        json={"name": "x" * (CRON_NAME_MAX_LEN + 1)},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "CRON_PROMPT_INVALID"


# --- negative cases: valid input must keep working -----------------------------


async def test_create_with_valid_bounds_still_succeeds(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={
            "trigger": "interval:60",
            "prompt": "  ping the server  ",
            "name": "x" * CRON_NAME_MAX_LEN,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["prompt"] == "ping the server"
    assert body["name"] == "x" * CRON_NAME_MAX_LEN

    r = await c.patch(
        f"/api/agents/{aid}/cron/{body['id']}",
        headers=alice_auth,
        json={"prompt": "x" * CRON_PROMPT_MAX_LEN},
    )
    assert r.status_code == 200, r.text
