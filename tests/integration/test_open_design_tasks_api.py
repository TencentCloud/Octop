"""Task snapshots are scoped to the conversation owner."""

from __future__ import annotations

import pytest

from tests.support.auth import create_user


@pytest.mark.asyncio
async def test_tasks_are_owned_and_readable_after_restart(env_with_agent):
    c, srv, auth, agent = env_with_agent
    created = await c.post(f"/api/agents/{agent}/threads", headers=auth, json={})
    assert created.status_code == 201
    thread_id = created.json()["thread_id"]
    tasks = srv.app_runtime.agent_registry.connector_runtime.get("open-design").tasks
    row = srv.services.thread_repo.get(thread_id)
    assert row is not None
    await tasks.register(
        row.user_id,
        "connector",
        agent,
        thread_id,
        {"project": "p", "requestId": "request", "runId": None, "status": "submitting"},
    )
    path = f"/api/agents/{agent}/threads/{thread_id}/open-design/tasks"
    response = await c.get(path, headers=auth)
    assert response.status_code == 200
    assert len(response.json()) == 1 and response.json()[0]["status"] == "submitting"
    assert "credential" not in response.text
    other = await create_user(c, auth, username="design-other")
    denied = await c.get(path, headers=other)
    assert denied.status_code == 404
    assert (await c.get(path)).status_code == 401
