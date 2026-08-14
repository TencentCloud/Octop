"""Shared agent list and ownership behavior."""

from __future__ import annotations

import pytest

from tests.support.auth import create_user


@pytest.fixture
async def env(env_with_provider):
    yield env_with_provider


async def _shared_agent(env) -> tuple[object, dict[str, str], dict[str, str], str]:
    client, _srv, admin_auth = env
    owner_auth = await create_user(client, admin_auth, username="share_owner")
    peer_auth = await create_user(client, admin_auth, username="share_peer")
    response = await client.post(
        "/api/agents/from-expert/default",
        headers=owner_auth,
        json={"name": "shared-bot"},
    )
    assert response.status_code == 201, response.text
    return client, owner_auth, peer_auth, response.json()["agent_id"]


async def test_shared_agent_appears_for_other_user(env) -> None:
    client, owner_auth, peer_auth, agent_id = await _shared_agent(env)

    response = await client.patch(
        f"/api/agents/{agent_id}",
        headers=owner_auth,
        json={"is_shared": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_shared"] is True

    response = await client.get("/api/agents", headers=peer_auth)
    assert response.status_code == 200
    agents = {row["agent_id"]: row for row in response.json()}
    assert agent_id in agents
    assert agents[agent_id]["is_owner"] is False
    assert agents[agent_id]["owner_username"] == "share_owner"

    response = await client.get(f"/api/agents/{agent_id}", headers=peer_auth)
    assert response.status_code == 200
    assert response.json()["is_shared"] is True
    assert response.json()["is_owner"] is False


async def test_create_agent_can_be_shared(env) -> None:
    client, _srv, admin_auth = env
    owner_auth = await create_user(client, admin_auth, username="shared_create_owner")
    peer_auth = await create_user(client, admin_auth, username="shared_create_peer")

    response = await client.post(
        "/api/agents",
        headers=owner_auth,
        json={"name": "created-shared-bot", "config": {}, "is_shared": True},
    )
    assert response.status_code == 201, response.text
    agent_id = response.json()["agent_id"]
    assert response.json()["is_shared"] is True

    response = await client.get("/api/agents", headers=peer_auth)
    assert response.status_code == 200
    assert agent_id in {row["agent_id"] for row in response.json()}


async def test_peer_cannot_patch_shared_agent(env) -> None:
    client, owner_auth, peer_auth, agent_id = await _shared_agent(env)
    response = await client.patch(
        f"/api/agents/{agent_id}",
        headers=owner_auth,
        json={"is_shared": True},
    )
    assert response.status_code == 200, response.text

    response = await client.patch(
        f"/api/agents/{agent_id}",
        headers=peer_auth,
        json={"name": "hijack"},
    )
    assert response.status_code == 403


async def test_peer_cannot_mutate_shared_agent_workspace_or_skills(env) -> None:
    client, owner_auth, peer_auth, agent_id = await _shared_agent(env)
    response = await client.patch(
        f"/api/agents/{agent_id}",
        headers=owner_auth,
        json={"is_shared": True},
    )
    assert response.status_code == 200, response.text

    response = await client.put(
        f"/api/agents/{agent_id}/workspace/file",
        headers=peer_auth,
        params={"path": "SOUL.md"},
        json={"content": "peer mutation"},
    )
    assert response.status_code == 403

    response = await client.post(
        f"/api/agents/{agent_id}/skills/example/disable",
        headers=peer_auth,
    )
    assert response.status_code == 403

    response = await client.post(
        "/api/mbti/apply",
        headers={**peer_auth, "X-Octop-Agent-Id": agent_id},
        json={"code": "INTJ"},
    )
    assert response.status_code == 403

    response = await client.get(
        f"/api/agents/{agent_id}/terminal/context",
        headers=peer_auth,
    )
    assert response.status_code == 403

    response = await client.get(
        f"/api/agents/{agent_id}/chat/welcome",
        headers=peer_auth,
    )
    assert response.status_code == 200, response.text
    assert "welcome_message" in response.json()

    response = await client.get(f"/api/agents/{agent_id}/threads", headers=peer_auth)
    assert response.status_code == 200, response.text


async def test_peer_can_read_shared_agent_inbound_attachment(env) -> None:
    client, owner_auth, peer_auth, agent_id = await _shared_agent(env)
    response = await client.patch(
        f"/api/agents/{agent_id}",
        headers=owner_auth,
        json={"is_shared": True},
    )
    assert response.status_code == 200, response.text

    response = await client.put(
        f"/api/agents/{agent_id}/workspace/file",
        headers=owner_auth,
        params={"path": "inbound/shared-attachment.txt"},
        json={"content": "shared attachment"},
    )
    assert response.status_code == 200, response.text

    response = await client.get(
        f"/api/agents/{agent_id}/workspace/file",
        headers=peer_auth,
        params={"path": "inbound/shared-attachment.txt"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "shared attachment"

    response = await client.get(
        f"/api/agents/{agent_id}/workspace/download",
        headers=peer_auth,
        params={"path": "inbound/shared-attachment.txt"},
    )
    assert response.status_code == 200, response.text
    assert response.content == b"shared attachment"


async def test_unshare_hides_agent_from_peer(env) -> None:
    client, owner_auth, peer_auth, agent_id = await _shared_agent(env)
    response = await client.patch(
        f"/api/agents/{agent_id}",
        headers=owner_auth,
        json={"is_shared": True},
    )
    assert response.status_code == 200, response.text

    response = await client.patch(
        f"/api/agents/{agent_id}",
        headers=owner_auth,
        json={"is_shared": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_shared"] is False

    response = await client.get("/api/agents", headers=peer_auth)
    assert response.status_code == 200
    assert agent_id not in {row["agent_id"] for row in response.json()}

    response = await client.get(f"/api/agents/{agent_id}", headers=peer_auth)
    assert response.status_code == 403


async def test_shared_agent_threads_are_private(env) -> None:
    client, owner_auth, peer_auth, agent_id = await _shared_agent(env)
    response = await client.patch(
        f"/api/agents/{agent_id}",
        headers=owner_auth,
        json={"is_shared": True},
    )
    assert response.status_code == 200, response.text

    response = await client.post(f"/api/agents/{agent_id}/threads", headers=owner_auth)
    assert response.status_code == 201, response.text
    owner_thread_id = response.json()["thread_id"]

    response = await client.post(f"/api/agents/{agent_id}/threads", headers=peer_auth)
    assert response.status_code == 201, response.text
    peer_thread_id = response.json()["thread_id"]

    response = await client.get(f"/api/agents/{agent_id}/threads", headers=peer_auth)
    assert response.status_code == 200, response.text
    assert {thread["thread_id"] for thread in response.json()} == {peer_thread_id}

    response = await client.get(
        f"/api/agents/{agent_id}/threads/{owner_thread_id}/history",
        headers=peer_auth,
    )
    assert response.status_code == 403


async def test_peer_cannot_rebind_session_to_owner_thread(env) -> None:
    client, owner_auth, peer_auth, agent_id = await _shared_agent(env)
    response = await client.patch(
        f"/api/agents/{agent_id}",
        headers=owner_auth,
        json={"is_shared": True},
    )
    assert response.status_code == 200, response.text

    response = await client.post(f"/api/agents/{agent_id}/threads", headers=owner_auth)
    assert response.status_code == 201, response.text
    owner_thread_id = response.json()["thread_id"]

    response = await client.patch(
        f"/api/agents/{agent_id}/session",
        headers=peer_auth,
        json={"thread_id": owner_thread_id},
    )
    assert response.status_code == 403
