"""tests/integration/test_memory_api.py — dashboard memory router.

End-to-end smoke: build a real OctopServer with a main agent, seed a
small graph (entity / candidate / atom / episode / journal) directly
into ``~/.octop/agents/<id>/memory.sqlite`` via ``harness_memory.Memory``,
then drive the FastAPI router and assert the JSON shapes.

We bypass the harness-agent middleware (``capture`` / ``extract``)
because the dashboard surface is purely read-side; this keeps the
test fast and deterministic without an LLM.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

# `harness_memory` is an optional dependency (lazy-imported by the app); the
# real package is not part of the base install, so skip these integration
# tests when it is unavailable rather than failing the whole suite. The app
# reaches memory through the JSON-RPC bridge, so gate on that exact import
# target (the old ``harness_memory.lightclaw`` name no longer exists and made
# this whole file silently skip).
pytest.importorskip("harness_memory.adapters.bridge.handlers")

from octop.api.common.memory_client import (
    invalidate_cached_memory,
    memory_db_path,
    memory_namespace,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _seed_memory(srv: Any, agent_id: str) -> None:
    """Populate the agent's memory.sqlite with one row per layer."""
    from harness_memory.core import Memory  # noqa: PLC0415
    from harness_memory.types import (  # noqa: PLC0415
        AtomCard,
        Candidate,
        Entity,
        Episode,
        JournalEntry,
        RawEvent,
    )

    workspace = srv.services.paths.ensure_agent_workspace(agent_id)
    db_path = memory_db_path(workspace)
    namespace = memory_namespace(agent_id)

    memory = Memory(
        namespace=namespace,
        backend="sqlite",
        backend_config={"db_path": str(db_path)},
    )

    entity = Entity(
        id="ent-user",
        entity_type="User",
        canonical_name="User",
        aliases=[],
        atom_count=0,
        created_at=_now(),
    )
    memory.add_entity(entity)

    candidate = Candidate(
        id="cand-1",
        raw_event_ids=[],
        candidate_type="Preference",
        status="promoted",
        title="美式咖啡偏好",
        assertion="喜欢喝美式咖啡",
        verbatim_quote="喜欢喝美式咖啡",
        quote_event_id="",
        subject_name="user",
        subject_entity_type="User",
        target_entity_id="ent-user",
        confidence="high",
        importance="high",
        recommended_action="promote",
        promotion_reason="seed",
        extractor_version="test",
        created_at=_now(),
    )
    memory.add_candidate(candidate)

    atom = AtomCard(
        id="atom-1",
        entity_id="ent-user",
        candidate_id="cand-1",
        raw_event_ids=[],
        assertion="喜欢喝美式咖啡",
        verbatim_quote="喜欢喝美式咖啡",
        quote_event_id="",
        search_terms=["coffee", "americano"],
        occurred_at=_now(),
        confidence="high",
        importance="high",
        created_at=_now(),
    )
    memory.add_atom(atom)

    memory.add_raw_batch(
        [
            RawEvent(
                id="raw-1",
                host="octop",
                session_id="sess-1",
                thread_id="th-1",
                user="u",
                timestamp=_now(),
                event_type="user_message",
                content="我喜欢喝美式咖啡",
            ),
            RawEvent(
                id="raw-2",
                host="octop",
                session_id="sess-1",
                thread_id="th-1",
                user="u",
                timestamp=_now(),
                event_type="assistant_message",
                content="好的，记住了",
            ),
        ]
    )

    episode = Episode(
        id="ep-1",
        raw_event_ids=[],
        occurred_at=_now(),
        summary="用户表达对美式咖啡的偏好",
        verbatim_quote="喜欢喝美式咖啡",
        quote_event_id="",
        emotion="happy",
        intensity=2,
        people=[],
        topics=["饮品"],
        extractor_version="test",
        created_at=_now(),
    )
    memory.add_episodes([episode])

    memory.append_journal(
        JournalEntry(
            id="j-1",
            timestamp=_now(),
            action="promote",
            actor="auto",
            target_entity_id="ent-user",
            target_atom_id="atom-1",
            target_candidate_id="cand-1",
            note="seed",
        )
    )
    # Drop any cached memory in the dashboard cache so the router sees
    # the fresh seed rows on its first request.
    invalidate_cached_memory(agent_id)


@pytest.mark.asyncio
async def test_stats_counts(env_with_main_agent) -> None:
    client, srv, auth, aid = env_with_main_agent
    _seed_memory(srv, aid)

    r = await client.get(f"/api/agents/{aid}/memory/stats/counts", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["atoms"] == 1
    assert body["entities"] == 1
    assert body["episodes"] == 1
    assert body["candidates_pending"] == 0
    assert body["atoms_delta_7d"] == 1


@pytest.mark.asyncio
async def test_list_atoms_returns_kind(env_with_main_agent) -> None:
    client, srv, auth, aid = env_with_main_agent
    _seed_memory(srv, aid)

    r = await client.post(f"/api/agents/{aid}/memory/atoms/list", headers=auth, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == "atom-1"
    assert item["kind"] == "Preference"


@pytest.mark.asyncio
async def test_get_atom_inline_kind(env_with_main_agent) -> None:
    client, srv, auth, aid = env_with_main_agent
    _seed_memory(srv, aid)

    r = await client.get(f"/api/agents/{aid}/memory/atoms/atom-1", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assertion"] == "喜欢喝美式咖啡"
    assert body["kind"] == "Preference"


@pytest.mark.asyncio
async def test_get_atom_404(env_with_main_agent) -> None:
    client, _srv, auth, aid = env_with_main_agent
    r = await client.get(f"/api/agents/{aid}/memory/atoms/no-such-id", headers=auth)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_terminal_about_me(env_with_main_agent) -> None:
    client, srv, auth, aid = env_with_main_agent
    _seed_memory(srv, aid)

    r = await client.get(f"/api/agents/{aid}/memory/terminal/about_me", headers=auth)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["assertion"] == "喜欢喝美式咖啡"
    assert items[0]["kind"] == "Preference"


@pytest.mark.asyncio
async def test_recent_journal(env_with_main_agent) -> None:
    client, srv, auth, aid = env_with_main_agent
    _seed_memory(srv, aid)

    r = await client.get(f"/api/agents/{aid}/memory/journal/recent?limit=5", headers=auth)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["action"] == "promote"


@pytest.mark.asyncio
async def test_deprecate_atom_round_trip(env_with_main_agent) -> None:
    client, srv, auth, aid = env_with_main_agent
    _seed_memory(srv, aid)

    r = await client.post(
        f"/api/agents/{aid}/memory/atoms/atom-1:deprecate",
        headers=auth,
        json={"reason": "outdated"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "deprecated"

    # A second deprecate of the same atom returns 404 (already deprecated).
    r2 = await client.post(
        f"/api/agents/{aid}/memory/atoms/atom-1:deprecate",
        headers=auth,
        json={"reason": "again"},
    )
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_list_raw_events(env_with_main_agent) -> None:
    client, srv, auth, aid = env_with_main_agent
    _seed_memory(srv, aid)

    r = await client.post(f"/api/agents/{aid}/memory/raw_events/list", headers=auth, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert {i["id"] for i in body["items"]} == {"raw-1", "raw-2"}

    # event_type filter narrows to the user message.
    r2 = await client.post(
        f"/api/agents/{aid}/memory/raw_events/list",
        headers=auth,
        json={"event_type": "user_message"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["id"] == "raw-1"


@pytest.mark.asyncio
async def test_extract_config_defaults_then_update(env_with_main_agent) -> None:
    client, _srv, auth, aid = env_with_main_agent

    # GET returns defaults for a fresh agent.
    r = await client.get(f"/api/agents/{aid}/memory/extract-config", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["memory_enabled"] is True
    assert r.json()["extract_trigger_mode"] == "idle"
    assert r.json()["extract_idle_seconds"] == 300.0

    # PUT switches to interval mode; short interval is clamped to the floor.
    r2 = await client.put(
        f"/api/agents/{aid}/memory/extract-config",
        headers=auth,
        json={
            "memory_enabled": False,
            "extract_trigger_mode": "interval",
            "extract_interval_seconds": 5,
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["memory_enabled"] is False
    assert r2.json()["extract_trigger_mode"] == "interval"
    assert r2.json()["extract_interval_seconds"] == 300.0  # clamped to 5-min floor

    # GET reflects the persisted change.
    r3 = await client.get(f"/api/agents/{aid}/memory/extract-config", headers=auth)
    assert r3.json()["extract_trigger_mode"] == "interval"
    assert r3.json()["extract_interval_seconds"] == 300.0
    assert r3.json()["memory_enabled"] is False


@pytest.mark.asyncio
async def test_extract_config_rejects_bad_mode(env_with_main_agent) -> None:
    client, _srv, auth, aid = env_with_main_agent
    r = await client.put(
        f"/api/agents/{aid}/memory/extract-config",
        headers=auth,
        json={"extract_trigger_mode": "bogus"},
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_extract_config_clamps_zero_idle_time_to_one_minute(
    env_with_main_agent,
) -> None:
    client, _srv, auth, aid = env_with_main_agent
    r = await client.put(
        f"/api/agents/{aid}/memory/extract-config",
        headers=auth,
        json={"extract_trigger_mode": "idle", "extract_idle_seconds": 0},
    )
    assert r.status_code == 200, r.text
    assert r.json()["extract_idle_seconds"] == 60.0


@pytest.mark.asyncio
async def test_unauthenticated(env_with_main_agent) -> None:
    client, _srv, _auth, aid = env_with_main_agent
    # No auth headers → must be rejected by the auth middleware.
    r = await client.get(f"/api/agents/{aid}/memory/stats/counts")
    assert r.status_code in (401, 403)
