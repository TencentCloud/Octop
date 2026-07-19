"""tests/integration/test_usage_api.py — token usage ledger + summary endpoint.

Three layers:
  1. UsageRepo round-trips rows and aggregates per granularity.
  2. /api/usage/summary respects ?as_user= scope (admin) and pins
     non-admins to their own user_id.
  3. /api/admin/usage/summary returns global rollups.

The chat-stream → ledger pipe is exercised in test_chat_ws via the
existing FakeHarnessAgent fixtures; here we drive the repo directly so
the test stays focused.
"""

from __future__ import annotations

import time
from typing import Any

import pytest


@pytest.fixture
async def env(env_usage):
    _c, srv, _admin_auth, _alice_auth, ctx = env_usage
    # The usage_log table has FOREIGN KEYs to agents(agent_id) and users(id).
    # These tests log against synthetic agent ids, so seed matching parent
    # rows up front (users alice_id / 1 already exist from bootstrap).
    _seed_usage_agents(srv, ["agt1", "agt-a", "agt-b", "x", "y"], user_id=ctx["alice_id"])
    yield env_usage


def _seed_usage_agents(srv: Any, agent_ids: list[str], *, user_id: int) -> None:
    with srv.services.db.connect() as conn:
        now = int(time.time())
        for aid in agent_ids:
            conn.execute(
                "INSERT OR IGNORE INTO agents (agent_id, user_id, name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (aid, user_id, aid, now, now),
            )


# --- repo direct -------------------------------------------------------------


async def test_repo_record_and_summary_total(env: Any) -> None:
    _c, srv, _admin_auth, _alice_auth, ctx = env
    repo = srv.services.usage_repo
    repo.record(
        agent_id="agt1",
        user_id=ctx["alice_id"],
        thread_id="t1",
        model="openai:gpt-4o-mini",
        input_tokens=100,
        output_tokens=50,
    )
    repo.record(
        agent_id="agt1",
        user_id=ctx["alice_id"],
        thread_id="t1",
        model="openai:gpt-4o-mini",
        input_tokens=200,
        output_tokens=80,
    )
    result = repo.summary(user_id=ctx["alice_id"], window="last_30d", granularity="total")
    assert result["input_tokens"] == 300
    assert result["output_tokens"] == 130
    assert result["total_tokens"] == 430
    assert result["turns"] == 2
    assert result["avg_per_turn"] == 215


async def test_repo_summary_by_agent(env: Any) -> None:
    _c, srv, _admin_auth, _alice_auth, ctx = env
    repo = srv.services.usage_repo
    repo.record(agent_id="agt-a", user_id=ctx["alice_id"], input_tokens=10, output_tokens=5)
    repo.record(agent_id="agt-a", user_id=ctx["alice_id"], input_tokens=20, output_tokens=10)
    repo.record(agent_id="agt-b", user_id=ctx["alice_id"], input_tokens=5, output_tokens=2)
    result = repo.summary(user_id=ctx["alice_id"], window="last_30d", granularity="by_agent")
    by_id = {b["key"]: b for b in result["buckets"]}
    assert by_id["agt-a"]["total_tokens"] == 45
    assert by_id["agt-b"]["total_tokens"] == 7


async def test_repo_summary_by_model(env: Any) -> None:
    _c, srv, _admin_auth, _alice_auth, ctx = env
    repo = srv.services.usage_repo
    repo.record(
        agent_id="x",
        user_id=ctx["alice_id"],
        model="openai:gpt-4o-mini",
        input_tokens=10,
        output_tokens=5,
    )
    repo.record(
        agent_id="x",
        user_id=ctx["alice_id"],
        model="anthropic:claude-haiku",
        input_tokens=20,
        output_tokens=10,
    )
    repo.record(
        agent_id="x",
        user_id=ctx["alice_id"],
        model="",  # unknown — should bucket as ``(unknown)``
        input_tokens=1,
        output_tokens=1,
    )
    result = repo.summary(user_id=ctx["alice_id"], window="last_30d", granularity="by_model")
    by_key = {b["key"]: b for b in result["buckets"]}
    assert by_key["openai:gpt-4o-mini"]["turns"] == 1
    assert by_key["anthropic:claude-haiku"]["total_tokens"] == 30
    assert "(unknown)" in by_key


# --- /api/usage/summary -----------------------------------------------------


async def test_user_summary_only_sees_own_data(env: Any) -> None:
    """Non-admin caller is implicitly scoped to their own user_id."""
    c, srv, admin_auth, alice_auth, ctx = env
    repo = srv.services.usage_repo
    # admin's own row (user_id=1)
    repo.record(agent_id="x", user_id=1, input_tokens=1000, output_tokens=500)
    # alice's row
    repo.record(agent_id="y", user_id=ctx["alice_id"], input_tokens=10, output_tokens=5)

    r = await c.get("/api/usage/summary?granularity=total", headers=alice_auth)
    assert r.status_code == 200
    body = r.json()
    assert body["total_tokens"] == 15
    assert body["turns"] == 1


async def test_admin_can_query_other_user_via_as_user(env: Any) -> None:
    c, srv, admin_auth, _alice_auth, ctx = env
    repo = srv.services.usage_repo
    repo.record(agent_id="y", user_id=ctx["alice_id"], input_tokens=10, output_tokens=5)

    r = await c.get(
        f"/api/usage/summary?granularity=total&as_user={ctx['alice_id']}",
        headers=admin_auth,
    )
    assert r.status_code == 200
    assert r.json()["total_tokens"] == 15


async def test_non_admin_as_user_is_forbidden(env: Any) -> None:
    c, _srv, _admin_auth, alice_auth, _ctx = env
    r = await c.get(
        "/api/usage/summary?as_user=1",
        headers=alice_auth,
    )
    assert r.status_code == 403


async def test_admin_summary_global(env: Any) -> None:
    c, srv, admin_auth, _alice_auth, ctx = env
    repo = srv.services.usage_repo
    repo.record(agent_id="x", user_id=1, input_tokens=100, output_tokens=50)
    repo.record(agent_id="y", user_id=ctx["alice_id"], input_tokens=10, output_tokens=5)
    r = await c.get(
        "/api/admin/usage/summary?granularity=total",
        headers=admin_auth,
    )
    assert r.status_code == 200
    assert r.json()["total_tokens"] == 165


async def test_admin_summary_requires_admin(env: Any) -> None:
    c, _srv, _admin_auth, alice_auth, _ctx = env
    r = await c.get("/api/admin/usage/summary", headers=alice_auth)
    assert r.status_code == 403


# --- chunk extraction in chat router ---------------------------------------


def test_extract_usage_from_chunk_direct() -> None:
    from octop.api.routers.chat.turn import extract_usage_from_chunk as _extract_usage_from_chunk

    chunk = {"usage": {"input_tokens": 7, "output_tokens": 3}}
    assert _extract_usage_from_chunk(chunk) == {"input_tokens": 7, "output_tokens": 3}


def test_extract_usage_from_state_snapshot_dict_message() -> None:
    from octop.api.routers.chat.turn import extract_usage_from_chunk as _extract_usage_from_chunk

    chunk = {
        "type": "state_snapshot",
        "data": {
            "messages": [
                {"role": "user", "content": "hi"},
                {
                    "role": "assistant",
                    "content": "hello!",
                    "usage_metadata": {"input_tokens": 9, "output_tokens": 4},
                    "response_metadata": {"model_name": "openai:gpt-4o-mini"},
                },
            ],
        },
    }
    out = _extract_usage_from_chunk(chunk)
    assert out is not None
    assert out["input_tokens"] == 9
    assert out["output_tokens"] == 4
    assert out["model"] == "openai:gpt-4o-mini"


def test_extract_usage_returns_none_when_absent() -> None:
    from octop.api.routers.chat.turn import extract_usage_from_chunk as _extract_usage_from_chunk

    assert _extract_usage_from_chunk({"type": "token", "content": "hi"}) is None
    assert _extract_usage_from_chunk({"type": "state_snapshot", "data": {}}) is None
    assert _extract_usage_from_chunk(None) is None  # type: ignore[arg-type]
