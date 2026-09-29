"""GET /api/agents/overview — kanban fields on the agent list."""

from __future__ import annotations

from tests.support.auth import resolve_user_id

_KANBAN_STATUSES = {"needs_you", "working", "done", "idle"}


async def _overview(client, auth) -> dict[str, dict]:
    response = await client.get("/api/agents/overview", headers=auth)
    assert response.status_code == 200, response.text
    return {row["agent_id"]: row for row in response.json()}


async def test_overview_returns_kanban_fields(env_with_main_agent) -> None:
    client, _srv, auth, agent_id = env_with_main_agent
    rows = await _overview(client, auth)
    assert agent_id in rows
    row = rows[agent_id]
    assert row["kanban_status"] in _KANBAN_STATUSES
    assert isinstance(row["busy"], bool)
    assert row["hitl_pending"] is None
    assert row["pending_plan"] is False
    assert "latest_thread" in row
    assert isinstance(row["unread_count"], int)
    # /overview must not shadow the /{agent_id} detail route
    detail = await client.get(f"/api/agents/{agent_id}", headers=auth)
    assert detail.status_code == 200


async def test_overview_unread_lands_in_done_bucket(env_with_main_agent) -> None:
    client, srv, auth, agent_id = env_with_main_agent
    # The bootstrap agent is "failed" in the provider-less test env; make the
    # lifecycle state deterministic so this test targets the unread signal.
    srv.services.agent_repo.set_state(agent_id, "running")
    user_id = await resolve_user_id(client, auth, "admin")
    key = f"{agent_id}:dashboard:kanban-test"
    srv.services.thread_repo.insert(
        thread_id="t-kanban",
        agent_id=agent_id,
        user_id=user_id,
        channel_type="dashboard",
        session_key=key,
        title="kanban chat",
    )
    srv.services.session_repo.upsert(
        session_key=key,
        agent_id=agent_id,
        user_id=user_id,
        channel_type="dashboard",
        chat_type="single",
        thread_id="t-kanban",
    )
    srv.services.session_repo.increment_unread(key)

    rows = await _overview(client, auth)
    row = rows[agent_id]
    assert row["unread_count"] == 1
    assert row["kanban_status"] == "done"
    assert row["latest_thread"] is not None
    assert row["latest_thread"]["thread_id"] == "t-kanban"
