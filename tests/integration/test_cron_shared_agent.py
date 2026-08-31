"""Cron jobs on shared agents are scoped to the acting user."""

from __future__ import annotations

from tests.support.auth import create_agent, create_user, seed_openai_provider


async def test_peer_can_create_own_cron_on_shared_agent(env) -> None:
    client, _srv, admin_auth = env
    await seed_openai_provider(client, admin_auth)
    owner_auth = await create_user(client, admin_auth, username="cron_owner")
    peer_auth = await create_user(client, admin_auth, username="cron_peer")
    other_auth = await create_user(client, admin_auth, username="cron_other")
    agent_id = await create_agent(client, owner_auth, name="shared-cron-bot")

    response = await client.patch(
        f"/api/agents/{agent_id}",
        headers=owner_auth,
        json={"is_shared": True},
    )
    assert response.status_code == 200, response.text

    response = await client.post(
        f"/api/agents/{agent_id}/cron",
        headers=peer_auth,
        json={
            "name": "Peer morning brief",
            "trigger": "cron:0 9 * * *",
            "prompt": "Summarize today's calendar",
            "enabled": False,
            "task_type": "agent",
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["name"] == "Peer morning brief"
    assert created["enabled"] is False

    response = await client.get(f"/api/agents/{agent_id}/cron", headers=peer_auth)
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()] == [created["id"]]

    response = await client.get(f"/api/agents/{agent_id}/cron", headers=other_auth)
    assert response.status_code == 200, response.text
    assert response.json() == []

    response = await client.get(
        f"/api/agents/{agent_id}/cron/{created['id']}",
        headers=other_auth,
    )
    assert response.status_code == 403
