"""Published expert HTTP API integration coverage."""

from __future__ import annotations

from typing import Any

from tests.support.auth import create_agent, create_user


async def _owner_and_peer(
    env: tuple[Any, Any, dict[str, str]],
) -> tuple[Any, Any, dict[str, str], dict[str, str], str]:
    client, server, admin_auth = env
    owner_auth = await create_user(client, admin_auth, username="publish_owner")
    peer_auth = await create_user(client, admin_auth, username="publish_peer")
    created = await client.post(
        "/api/agents/from-expert/default",
        headers=owner_auth,
        json={"name": "publish-source"},
    )
    assert created.status_code == 201, created.text
    return client, server, owner_auth, peer_auth, created.json()["agent_id"]


async def test_publish_list_install_and_unpublish_preserves_installed_fork(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, owner_auth, peer_auth, source_agent_id = await _owner_and_peer(env)

    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Published default", "description": "A private forkable expert"},
    )
    assert published.status_code == 201, published.text
    expert = published.json()
    expert_id = expert["id"]
    assert expert["creator_username"] == "publish_owner"

    listed = await client.get("/api/experts/published", headers=peer_auth)
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [expert_id]

    detail = await client.get(f"/api/experts/published/{expert_id}", headers=peer_auth)
    assert detail.status_code == 200, detail.text
    assert "manifest.json" in detail.json()["files"]

    installed = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=peer_auth,
        json={"name": "Peer installed expert", "description": "Peer copy"},
    )
    assert installed.status_code == 201, installed.text
    installed_agent_id = installed.json()["agent_id"]
    assert installed.json()["user_id"] != expert["created_by"]

    denied = await client.delete(f"/api/experts/published/{expert_id}", headers=peer_auth)
    assert denied.status_code == 403, denied.text

    unpublished = await client.delete(f"/api/experts/published/{expert_id}", headers=owner_auth)
    assert unpublished.status_code == 204, unpublished.text
    assert (await client.get("/api/experts/published", headers=peer_auth)).json() == []

    fork = await client.get(f"/api/agents/{installed_agent_id}", headers=peer_auth)
    assert fork.status_code == 200, fork.text
    assert fork.json()["name"] == "Peer installed expert"


async def test_install_published_expert_accepts_create_options(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, owner_auth, peer_auth, source_agent_id = await _owner_and_peer(env)

    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Parametric published", "description": "source"},
    )
    assert published.status_code == 201, published.text
    expert_id = published.json()["id"]

    installed = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=peer_auth,
        json={
            "name": "Installed with options",
            "description": "fork with options",
            "default_model": "openai/gpt-4o-mini",
            "max_iters": 12,
            "backend": {"type": "local_shell"},
        },
    )
    assert installed.status_code == 201, installed.text
    agent_id = installed.json()["agent_id"]

    detail = await client.get(f"/api/agents/{agent_id}", headers=peer_auth)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["name"] == "Installed with options"
    assert body["default_model"] == "openai/gpt-4o-mini"
    assert body.get("max_iters") == 12
    config = body.get("config") or {}
    assert (config.get("backend") or {}).get("type") == "local_shell"


async def test_creator_can_refresh_published_expert(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, owner_auth, _peer_auth, source_agent_id = await _owner_and_peer(env)
    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Refreshable expert"},
    )
    assert published.status_code == 201, published.text
    before = published.json()["updated_at"]

    refreshed = await client.post(
        f"/api/experts/published/{published.json()['id']}/refresh",
        headers=owner_auth,
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["id"] == published.json()["id"]
    assert refreshed.json()["updated_at"] >= before


async def test_second_publish_of_same_source_is_rejected(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, owner_auth, _peer_auth, source_agent_id = await _owner_and_peer(env)
    first = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "First publish"},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Duplicate publish"},
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "PUBLISHED_EXPERT_ALREADY_EXISTS"


async def test_admin_cannot_publish_another_users_agent(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, admin_auth = env
    owner_auth = await create_user(client, admin_auth, username="private_agent_owner")
    created = await client.post(
        "/api/agents/from-expert/default",
        headers=owner_auth,
        json={"name": "private source"},
    )
    assert created.status_code == 201, created.text

    published = await client.post(
        f"/api/agents/{created.json()['agent_id']}/publish-expert",
        headers=admin_auth,
        json={"name": "Admin must not publish"},
    )
    assert published.status_code == 403, published.text


async def test_publish_without_skill_details_blocks_peer_view_and_edit(
    env_with_provider: tuple[Any, Any, dict[str, str]],
) -> None:
    client, server, admin_auth = env_with_provider
    owner_auth = await create_user(client, admin_auth, username="guarded_owner")
    peer_auth = await create_user(client, admin_auth, username="guarded_peer")
    source_agent_id = await create_agent(client, owner_auth)

    # Seed a workspace skill directly via the workspace backend so the test
    # does not depend on the source agent being started.
    workspace = server.app_runtime.agent_registry.workspace_for_agent(source_agent_id)
    assert workspace is not None
    await workspace.aupload_many(
        [
            (
                "skills/secret-flow/SKILL.md",
                (
                    b"---\nname: secret-flow\ndescription: Secret workflow\n---\n"
                    b"# Secret steps\nDo the thing.\n"
                ),
            )
        ]
    )

    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Guarded expert", "allow_skill_details": False},
    )
    assert published.status_code == 201, published.text
    assert published.json()["allow_skill_details"] is False
    expert_id = published.json()["id"]

    # Snapshot preview hides skill files from peers but not from the publisher.
    peer_detail = await client.get(f"/api/experts/published/{expert_id}", headers=peer_auth)
    assert peer_detail.status_code == 200, peer_detail.text
    assert not any(p.startswith("skills/") for p in peer_detail.json()["files"])
    owner_detail = await client.get(f"/api/experts/published/{expert_id}", headers=owner_auth)
    assert any(p.startswith("skills/") for p in owner_detail.json()["files"])

    installed = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=peer_auth,
        json={"name": "Peer guarded install"},
    )
    assert installed.status_code == 201, installed.text
    agent_id = installed.json()["agent_id"]

    listed = await client.get(f"/api/agents/{agent_id}/skills", headers=peer_auth)
    assert listed.status_code == 200, listed.text
    summary = next(s for s in listed.json() if s.get("slug") == "secret-flow")
    assert summary["protected"] is True

    detail = await client.get(f"/api/agents/{agent_id}/skills/secret-flow", headers=peer_auth)
    assert detail.status_code == 403, detail.text
    assert detail.json()["error"]["code"] == "SKILL_DETAILS_PROTECTED"

    updated = await client.put(
        f"/api/agents/{agent_id}/skills/secret-flow",
        headers=peer_auth,
        json={"content": "---\nname: secret-flow\ndescription: hacked\n---\n"},
    )
    assert updated.status_code == 403, updated.text
    deleted = await client.delete(f"/api/agents/{agent_id}/skills/secret-flow", headers=peer_auth)
    assert deleted.status_code == 403, deleted.text

    # Raw workspace file access must not bypass the guard.
    raw_read = await client.get(
        f"/api/agents/{agent_id}/workspace/file",
        headers=peer_auth,
        params={"path": "skills/secret-flow/SKILL.md", "from_workspace": True},
    )
    assert raw_read.status_code == 403, raw_read.text

    # The publisher installing their own expert keeps full access.
    own_install = await client.post(
        f"/api/experts/published/{expert_id}/install",
        headers=owner_auth,
        json={"name": "Owner guarded install"},
    )
    assert own_install.status_code == 201, own_install.text
    own_agent = own_install.json()["agent_id"]
    own_detail = await client.get(f"/api/agents/{own_agent}/skills/secret-flow", headers=owner_auth)
    assert own_detail.status_code == 200, own_detail.text
    own_list = await client.get(f"/api/agents/{own_agent}/skills", headers=owner_auth)
    own_summary = next(s for s in own_list.json() if s.get("slug") == "secret-flow")
    assert own_summary["protected"] is False


async def test_refresh_can_toggle_allow_skill_details(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, owner_auth, _peer_auth, source_agent_id = await _owner_and_peer(env)
    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Toggleable expert", "allow_skill_details": False},
    )
    assert published.status_code == 201, published.text
    assert published.json()["allow_skill_details"] is False

    refreshed = await client.post(
        f"/api/experts/published/{published.json()['id']}/refresh",
        headers=owner_auth,
        json={"allow_skill_details": True},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["allow_skill_details"] is True
