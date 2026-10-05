"""Integration tests for /api/admin/security."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.support.auth import seed_openai_provider


@pytest.mark.asyncio
async def test_security_policy_save(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    client, auth = env_admin_client
    get_resp = await client.get("/api/admin/security", headers=auth)
    assert get_resp.status_code == 200, get_resp.text

    body: dict[str, Any] = {
        "hitl": {
            "enabled": False,
            "tools": ["bash", "execute", "write_file", "edit_file"],
            "allowed_decisions": ["approve", "reject"],
        },
        "filesystem": {
            "enabled": True,
            "rules": [
                {
                    "operations": ["read", "write"],
                    "paths": ["/etc/**"],
                    "mode": "deny",
                }
            ],
        },
        "pii": {
            "enabled": True,
            "strategy": "mask",
            "surfaces": ["input", "output", "tool_results"],
        },
        "skill_scan": {"mode": "warn"},
        "tool_guard": {"enabled": True, "mode": "warn"},
    }
    put_resp = await client.put("/api/admin/security", headers=auth, json=body)
    assert put_resp.status_code == 200, put_resp.text
    saved = put_resp.json()
    assert saved["hitl"]["enabled"] is False
    assert saved["tool_guard"]["mode"] == "warn"


@pytest.mark.asyncio
async def test_security_policy_save_with_running_agent(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
) -> None:
    """Saving policy rebuilds harness agents without failing the HTTP request."""
    client, _srv, auth = env
    await seed_openai_provider(client, auth)
    create_resp = await client.post(
        "/api/agents",
        headers=auth,
        json={
            "name": "sec-bot",
            "config": {"providers": ["openai"], "default_model": "openai:gpt-4o"},
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    agent_id = create_resp.json()["agent_id"]
    status = await client.get(f"/api/agents/{agent_id}/status", headers=auth)
    assert status.json()["state"] == "running"

    put_resp = await client.put(
        "/api/admin/security",
        headers=auth,
        json={"tool_guard": {"enabled": True, "mode": "warn"}},
    )
    assert put_resp.status_code == 200, put_resp.text


@pytest.mark.asyncio
async def test_settings_hitl_is_readable_by_regular_user(
    env_admin_alice: tuple[httpx.AsyncClient, Any, dict[str, str], dict[str, str]],
) -> None:
    client, _srv, admin_auth, alice_auth = env_admin_alice

    r = await client.get("/api/settings/hitl", headers=alice_auth)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "enabled": False,
        "tool_guard_require_approval": False,
        "show_approval_ui": False,
    }

    forbidden = await client.get("/api/admin/security", headers=alice_auth)
    assert forbidden.status_code == 403

    put = await client.put(
        "/api/admin/security",
        headers=admin_auth,
        json={"hitl": {"enabled": True}},
    )
    assert put.status_code == 200, put.text
    assert put.json()["hitl"]["enabled"] is True

    r = await client.get("/api/settings/hitl", headers=alice_auth)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "enabled": True,
        "tool_guard_require_approval": False,
        "show_approval_ui": True,
    }

    put = await client.put(
        "/api/admin/security",
        headers=admin_auth,
        json={
            "hitl": {"enabled": False},
            "tool_guard": {"enabled": True, "mode": "require_approval"},
        },
    )
    assert put.status_code == 200, put.text

    r = await client.get("/api/settings/hitl", headers=alice_auth)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "enabled": False,
        "tool_guard_require_approval": True,
        "show_approval_ui": True,
    }
