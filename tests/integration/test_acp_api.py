"""tests/integration/test_acp_api.py — ACP runner configuration API."""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.auth import create_agent, create_user, resolve_user_id


def _runner(command: str = "python", name: str = "my_runner") -> dict[str, Any]:
    return {
        "enabled": True,
        "command": command,
        "args": ["-m", name],
        "env": {"FOO": "bar"},
        "trusted": False,
        "tool_parse_mode": "call_title",
        "stdio_buffer_limit_bytes": 52428800,
    }


@pytest.fixture
async def env_alice_acp(env):
    """Regular (non-admin) user ``alice`` owning one agent, alongside the admin client."""
    client, srv, admin_auth, _admin_agent_id = env
    alice_auth = await create_user(client, admin_auth, username="alice")
    agent_id = await create_agent(client, alice_auth, name="acp-alice", config={})
    yield client, srv, admin_auth, alice_auth, agent_id


async def _alice_runners(client, auth, agent_id) -> dict[str, Any]:
    r = await client.get(f"/api/agents/{agent_id}/acp", headers=auth)
    assert r.status_code == 200
    return r.json()["runners"]


@pytest.fixture
async def env(env_acp_agent):
    yield env_acp_agent


async def test_acp_config_round_trip(env) -> None:
    c, _srv, auth, agent_id = env

    r = await c.get(f"/api/agents/{agent_id}/acp", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["tool_enabled"] is False
    assert "opencode" in body["runners"]

    payload = {
        "tool_enabled": True,
        "runners": {
            "opencode": {
                "enabled": True,
                "command": "opencode",
                "args": ["acp"],
                "env": {},
                "trusted": False,
                "tool_parse_mode": "update_detail",
                "stdio_buffer_limit_bytes": 52428800,
            },
        },
    }
    r = await c.put(f"/api/agents/{agent_id}/acp", headers=auth, json=payload)
    assert r.status_code == 200
    assert r.json()["tool_enabled"] is True
    assert r.json()["runners"]["opencode"]["enabled"] is True

    r = await c.get(f"/api/agents/{agent_id}/acp/opencode", headers=auth)
    assert r.status_code == 200
    assert r.json()["command"] == "opencode"


async def test_acp_custom_runner_crud(env) -> None:
    c, _srv, auth, agent_id = env

    runner = {
        "enabled": True,
        "command": "python",
        "args": ["-m", "my_runner"],
        "env": {"FOO": "bar"},
        "trusted": True,
        "tool_parse_mode": "call_title",
        "stdio_buffer_limit_bytes": 52428800,
    }
    r = await c.put(f"/api/agents/{agent_id}/acp/my_runner", headers=auth, json=runner)
    assert r.status_code == 200
    assert r.json()["env"]["FOO"] == "bar"

    r = await c.delete(f"/api/agents/{agent_id}/acp/my_runner", headers=auth)
    assert r.status_code == 204

    r = await c.get(f"/api/agents/{agent_id}/acp/my_runner", headers=auth)
    assert r.status_code == 404


async def test_acp_builtin_runner_cannot_delete(env) -> None:
    c, _srv, auth, agent_id = env
    r = await c.delete(f"/api/agents/{agent_id}/acp/opencode", headers=auth)
    assert r.status_code == 403


async def test_acp_tool_allowed_for_scoped_root_dir(env) -> None:
    """Directory sandbox does not block enabling outbound acp_runner."""
    c, _srv, auth, _agent_id = env
    from tests.support.auth import create_agent

    agent_id = await create_agent(
        c,
        auth,
        name="acp-scoped",
        config={
            "backend": {
                "type": "local_shell",
                "root_dir": "/tmp/octop-acp-scoped",
                "virtual_mode": True,
            }
        },
    )
    r = await c.put(
        f"/api/agents/{agent_id}/acp/tool",
        headers=auth,
        json={"tool_enabled": True},
    )
    assert r.status_code == 200
    assert r.json()["tool_enabled"] is True


async def test_non_admin_cannot_put_runner(env_alice_acp) -> None:
    """ACL/V1: a plain-function call drops ``Depends(require_admin())`` — runner writes stay admin-only."""
    c, _srv, _admin, alice, agent_id = env_alice_acp
    before = await _alice_runners(c, alice, agent_id)

    r = await c.put(f"/api/agents/{agent_id}/acp/pwn", headers=alice, json=_runner())
    assert r.status_code == 403
    # Fail closed: the rejected write must not reach the settings store.
    assert await _alice_runners(c, alice, agent_id) == before


async def test_non_admin_cannot_delete_runner(env_alice_acp) -> None:
    """ACL/V1: the same evaporating dependency let any owner delete a runner definition."""
    c, srv, admin, alice, agent_id = env_alice_acp
    alice_id = await resolve_user_id(c, admin, "alice")
    registry = srv.app_runtime.agent_registry
    assert registry is not None
    registry.acp_settings.save_runners(
        alice_id, {"alice_runner": _runner("python", "alice_runner")}
    )
    before = await _alice_runners(c, alice, agent_id)
    assert "alice_runner" in before

    r = await c.delete(f"/api/agents/{agent_id}/acp/alice_runner", headers=alice)
    assert r.status_code == 403
    # Fail closed: the rejected delete must leave the stored runner set untouched.
    assert await _alice_runners(c, alice, agent_id) == before


async def test_non_admin_cannot_put_config_with_runners(env_alice_acp) -> None:
    """ACL/V1: ``PUT /agents/{id}/acp`` saved global runners with no admin check at all."""
    c, _srv, _admin, alice, agent_id = env_alice_acp
    before = await _alice_runners(c, alice, agent_id)

    r = await c.put(
        f"/api/agents/{agent_id}/acp",
        headers=alice,
        json={"tool_enabled": True, "runners": {"pwn": _runner()}},
    )
    assert r.status_code == 403
    # Fail closed: neither the runner set nor the tool toggle may be written.
    assert await _alice_runners(c, alice, agent_id) == before


async def test_admin_can_still_write_runners_through_agent_routes(env) -> None:
    """Over-correction guard: the admin path must stay open on all three agent-scoped routes."""
    c, _srv, auth, agent_id = env

    r = await c.put(f"/api/agents/{agent_id}/acp/my_runner", headers=auth, json=_runner())
    assert r.status_code == 200
    assert r.json()["command"] == "python"

    r = await c.delete(f"/api/agents/{agent_id}/acp/my_runner", headers=auth)
    assert r.status_code == 204

    # ``save_runners`` replaces the whole set, so this goes last.
    r = await c.put(
        f"/api/agents/{agent_id}/acp",
        headers=auth,
        json={"tool_enabled": True, "runners": {"opencode": _runner("opencode", "opencode")}},
    )
    assert r.status_code == 200
    assert "opencode" in r.json()["runners"]


async def test_non_admin_owner_can_still_toggle_tool_enabled(env_alice_acp) -> None:
    """Over-broad gate guard: only the ``runners`` branch is admin-only, the owner toggle is not."""
    c, _srv, _admin, alice, agent_id = env_alice_acp
    runners_before = await _alice_runners(c, alice, agent_id)

    r = await c.put(f"/api/agents/{agent_id}/acp/tool", headers=alice, json={"tool_enabled": True})
    assert r.status_code == 200
    assert r.json()["tool_enabled"] is True

    r = await c.put(f"/api/agents/{agent_id}/acp", headers=alice, json={"tool_enabled": False})
    assert r.status_code == 200
    assert r.json()["tool_enabled"] is False
    assert r.json()["runners"] == runners_before


async def test_admin_builtin_runner_delete_still_rejected(env) -> None:
    """The built-in runner protection must survive the helper extraction."""
    c, _srv, auth, agent_id = env
    r = await c.delete(f"/api/agents/{agent_id}/acp/opencode", headers=auth)
    assert r.status_code == 403
    r = await c.get(f"/api/agents/{agent_id}/acp", headers=auth)
    assert r.status_code == 200
    assert "opencode" in r.json()["runners"]
