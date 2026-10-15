"""tests/integration/test_cron_prompt_validation.py — cron prompt/name input errors are 4xx.

``require_cron_prompt`` / ``require_cron_name`` reject blank prompts, over-long prompts and
over-long names with a plain ``ValueError``. The cron router called them unguarded, so the
application-wide ``Exception`` handler answered those requests with ``500 INTERNAL_ERROR``
while a bad trigger on the same endpoint already returns ``400 CRON_TRIGGER_INVALID``.
"""

from __future__ import annotations

from typing import Any

import pytest

from octop.infra.cron.task_type import CRON_NAME_MAX_LEN, CRON_PROMPT_MAX_LEN


@pytest.fixture
async def env(env_alice_bob_agent):
    yield env_alice_bob_agent


async def test_create_with_blank_prompt_returns_400(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={"trigger": "interval:60", "prompt": "   "},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"


async def test_create_with_overlong_prompt_returns_400(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={"trigger": "interval:60", "prompt": "x" * (CRON_PROMPT_MAX_LEN + 1)},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"


async def test_create_with_overlong_name_returns_400(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={
            "trigger": "interval:60",
            "prompt": "ping the server",
            "name": "x" * (CRON_NAME_MAX_LEN + 1),
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"


async def test_patch_with_blank_prompt_returns_400(env: Any) -> None:
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={"trigger": "interval:30", "prompt": "x"},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    r = await c.patch(f"/api/agents/{aid}/cron/{cid}", headers=alice_auth, json={"prompt": "  "})
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"


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
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"


async def test_valid_prompt_and_name_still_create(env: Any) -> None:
    """The 400 mapping must not swallow the happy path or the stored trimming."""
    c, _srv, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/cron",
        headers=alice_auth,
        json={"trigger": "interval:60", "prompt": "  ping the server  ", "name": "  ping  "},
    )
    assert r.status_code == 201, r.text
    assert r.json()["prompt"] == "ping the server"
    assert r.json()["name"] == "ping"
