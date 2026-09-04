"""Published expert HTTP API integration coverage."""

from __future__ import annotations

import os
from typing import Any

import pytest

from tests.support.auth import create_user

posix_only = pytest.mark.skipif(
    os.name != "posix", reason="local_shell backend workspace file ops unsupported on Windows"
)


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
    assert installed.json()["state"] == "starting"
    assert installed.json()["bootstrap_pending"] is True
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


@posix_only
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


@posix_only
async def test_install_keeps_source_quick_prompts_when_publish_body_omits_them(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, admin_auth = env
    owner_auth = await create_user(client, admin_auth, username="quickcard_owner")
    peer_auth = await create_user(client, admin_auth, username="quickcard_peer")
    created = await client.post(
        "/api/agents/from-expert/ai-coding-coach",
        headers=owner_auth,
        json={"name": "quickcard-source"},
    )
    assert created.status_code == 201, created.text
    source_agent_id = created.json()["agent_id"]

    source_welcome = await client.get(
        f"/api/agents/{source_agent_id}/chat/welcome",
        headers=owner_auth,
    )
    assert source_welcome.status_code == 200, source_welcome.text
    source_prompts = source_welcome.json()["quick_prompts"]
    assert source_prompts

    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={
            "name": "Quick card expert",
            "welcome_message": {"zh": "开始写代码吧", "en": "Let's write code"},
        },
    )
    assert published.status_code == 201, published.text

    installed = await client.post(
        f"/api/experts/published/{published.json()['id']}/install",
        headers=peer_auth,
        json={"name": "Quick card fork"},
    )
    assert installed.status_code == 201, installed.text

    unpublished = await client.delete(
        f"/api/experts/published/{published.json()['id']}",
        headers=owner_auth,
    )
    assert unpublished.status_code == 204, unpublished.text

    fork_welcome = await client.get(
        f"/api/agents/{installed.json()['agent_id']}/chat/welcome",
        headers=peer_auth,
    )
    assert fork_welcome.status_code == 200, fork_welcome.text
    assert fork_welcome.json()["quick_prompts"] == source_prompts


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


async def test_published_list_exposes_snapshot_avatar(
    env: tuple[Any, Any, dict[str, str]],
) -> None:
    client, _server, owner_auth, peer_auth, source_agent_id = await _owner_and_peer(env)

    uploaded = await client.post(
        f"/api/agents/{source_agent_id}/avatar",
        headers=owner_auth,
        files={"file": ("face.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text

    published = await client.post(
        f"/api/agents/{source_agent_id}/publish-expert",
        headers=owner_auth,
        json={"name": "Avatar published"},
    )
    assert published.status_code == 201, published.text
    expert_id = published.json()["id"]
    icon_url = published.json().get("icon_url")
    assert isinstance(icon_url, str)
    assert icon_url.startswith(f"/api/experts/published/{expert_id}/avatar")
    assert "v=" in icon_url

    listed = await client.get("/api/experts/published", headers=peer_auth)
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json() if item["id"] == expert_id)
    assert row["icon_url"] == icon_url

    got = await client.get(icon_url, headers=peer_auth)
    assert got.status_code == 200, got.text
    assert got.content == PNG
    assert got.headers["content-type"].startswith("image/png")


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
