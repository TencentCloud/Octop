"""Disable plugin tools via Admin Plugins API and Experts tool-settings."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

from tests.support.auth import create_user

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "echo-tool"


def _echo_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path in _FIXTURE.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=f"echo-tool/{path.relative_to(_FIXTURE).as_posix()}")
    return buf.getvalue()


async def _install_echo(client: Any, auth: dict[str, str]) -> None:
    r = await client.post(
        "/api/plugins/upload",
        files={"file": ("echo-tool.zip", _echo_zip(), "application/zip")},
        data={"force": "true"},
        headers=auth,
    )
    assert r.status_code == 200, r.text


async def _create_agent(client: Any, auth: dict[str, str], name: str) -> str:
    created = await client.post("/api/agents", headers=auth, json={"name": name})
    assert created.status_code == 201, created.text
    return str(created.json()["agent_id"])


def _assert_echo_disabled_on_harness(srv: Any, agent_id: str, *, disabled: bool) -> None:
    agent = srv.app_runtime.agent_registry.get_agent(agent_id)
    names = set(getattr(agent.config, "tools_disabled", frozenset()) or ())
    if disabled:
        assert "echo_message" in names
    else:
        assert "echo_message" not in names


async def test_disable_plugin_tool_via_admin_plugins_api(env_with_provider: Any) -> None:
    client, srv, auth = env_with_provider
    await _install_echo(client, auth)
    aid = await _create_agent(client, auth, "plugin-admin-disable")

    listed = await client.get(f"/api/plugins/agents/{aid}/tools", headers=auth)
    assert listed.status_code == 200, listed.text
    tools = listed.json()["tools"]
    echo = next(t for t in tools if t["name"] == "echo_message")
    assert echo["enabled"] is True

    patch = await client.patch(
        f"/api/plugins/agents/{aid}/tools",
        headers=auth,
        json={
            "plugins": {
                "echo-tool": {
                    "tools": {"echo_message": {"enabled": False, "config": {}}},
                }
            }
        },
    )
    assert patch.status_code == 200, patch.text

    cfg = srv.app_runtime.agent_registry.get_config(aid)
    assert cfg["plugins"]["echo-tool"]["tools"]["echo_message"]["enabled"] is False
    _assert_echo_disabled_on_harness(srv, aid, disabled=True)

    settings = await client.get(f"/api/agents/{aid}/tool-settings", headers=auth)
    assert settings.status_code == 200, settings.text
    assert all(t["source"] == "builtin" for t in settings.json()["tools"])


async def test_disable_plugin_tool_via_expert_tool_settings(env_with_provider: Any) -> None:
    client, srv, auth = env_with_provider
    await _install_echo(client, auth)
    aid = await _create_agent(client, auth, "expert-tool-disable")

    r = await client.patch(
        f"/api/agents/{aid}/tool-settings/echo_message",
        headers=auth,
        json={"enabled": False, "source": "plugin", "plugin_id": "echo-tool"},
    )
    assert r.status_code == 200, r.text
    cfg = srv.app_runtime.agent_registry.get_config(aid)
    assert cfg["plugins"]["echo-tool"]["tools"]["echo_message"]["enabled"] is False
    _assert_echo_disabled_on_harness(srv, aid, disabled=True)

    on = await client.patch(
        f"/api/agents/{aid}/tool-settings/echo_message",
        headers=auth,
        json={"enabled": True, "source": "plugin", "plugin_id": "echo-tool"},
    )
    assert on.status_code == 200, on.text
    cfg = srv.app_runtime.agent_registry.get_config(aid)
    assert cfg["plugins"]["echo-tool"]["tools"]["echo_message"]["enabled"] is True
    _assert_echo_disabled_on_harness(srv, aid, disabled=False)


async def test_admin_and_expert_share_plugin_tool_config(env_with_provider: Any) -> None:
    """Admin Plugins toggle and Experts Tools write the same agent config."""
    client, srv, auth = env_with_provider
    await _install_echo(client, auth)
    aid = await _create_agent(client, auth, "shared-plugin-config")

    await client.patch(
        f"/api/plugins/agents/{aid}/tools",
        headers=auth,
        json={
            "plugins": {
                "echo-tool": {
                    "tools": {
                        "echo_message": {
                            "enabled": False,
                            "config": {"prefix": "x"},
                        }
                    },
                }
            }
        },
    )
    await client.patch(
        f"/api/agents/{aid}/tool-settings/echo_message",
        headers=auth,
        json={"enabled": True, "source": "plugin", "plugin_id": "echo-tool"},
    )
    cfg = srv.app_runtime.agent_registry.get_config(aid)
    tool_cfg = cfg["plugins"]["echo-tool"]["tools"]["echo_message"]
    assert tool_cfg["enabled"] is True
    assert tool_cfg.get("config", {}).get("prefix") == "x"


async def test_agent_plugin_switch_defaults_on_and_preserves_tools(
    env_with_provider: Any,
) -> None:
    client, srv, auth = env_with_provider
    await _install_echo(client, auth)
    aid = await _create_agent(client, auth, "agent-plugin-switch")

    listed = await client.get(f"/api/plugins/agents/{aid}", headers=auth)
    assert listed.status_code == 200, listed.text
    plugin = next(p for p in listed.json()["plugins"] if p["id"] == "echo-tool")
    assert plugin["agent_enabled"] is True
    assert plugin["enabled"] is True

    configured = await client.patch(
        f"/api/plugins/agents/{aid}/tools",
        headers=auth,
        json={
            "plugins": {
                "echo-tool": {
                    "tools": {
                        "echo_message": {
                            "enabled": True,
                            "config": {"prefix": "kept"},
                        }
                    }
                }
            }
        },
    )
    assert configured.status_code == 200, configured.text

    off = await client.patch(
        f"/api/plugins/agents/{aid}",
        headers=auth,
        json={"plugins": {"echo-tool": {"enabled": False}}},
    )
    assert off.status_code == 200, off.text
    plugin = next(p for p in off.json()["plugins"] if p["id"] == "echo-tool")
    assert plugin["agent_enabled"] is False
    assert plugin["enabled"] is False
    _assert_echo_disabled_on_harness(srv, aid, disabled=True)

    cfg = srv.app_runtime.agent_registry.get_config(aid)
    tool_cfg = cfg["plugins"]["echo-tool"]["tools"]["echo_message"]
    assert tool_cfg == {"enabled": True, "config": {"prefix": "kept"}}

    on = await client.patch(
        f"/api/plugins/agents/{aid}",
        headers=auth,
        json={"plugins": {"echo-tool": {"enabled": True}}},
    )
    assert on.status_code == 200, on.text
    cfg = srv.app_runtime.agent_registry.get_config(aid)
    assert cfg["plugins"]["echo-tool"]["tools"]["echo_message"] == tool_cfg


async def test_global_plugin_disable_takes_priority(env_with_provider: Any) -> None:
    client, _srv, auth = env_with_provider
    await _install_echo(client, auth)
    aid = await _create_agent(client, auth, "global-plugin-off")

    off = await client.patch(
        "/api/plugins/echo-tool",
        headers=auth,
        json={"enabled": False},
    )
    assert off.status_code == 200, off.text

    listed = await client.get(f"/api/plugins/agents/{aid}", headers=auth)
    assert listed.status_code == 200, listed.text
    plugin = next(p for p in listed.json()["plugins"] if p["id"] == "echo-tool")
    assert plugin["global_enabled"] is False
    assert plugin["agent_enabled"] is True
    assert plugin["enabled"] is False


async def test_agent_plugin_endpoints_enforce_owner(env_with_provider: Any) -> None:
    client, _srv, admin_auth = env_with_provider
    await _install_echo(client, admin_auth)
    owner_auth = await create_user(client, admin_auth, username="plugin_owner")
    other_auth = await create_user(client, admin_auth, username="plugin_other")
    aid = await _create_agent(client, owner_auth, "owned-plugin-agent")

    listed = await client.get(f"/api/plugins/agents/{aid}", headers=other_auth)
    assert listed.status_code == 403, listed.text
    patched = await client.patch(
        f"/api/plugins/agents/{aid}",
        headers=other_auth,
        json={"plugins": {"echo-tool": {"enabled": False}}},
    )
    assert patched.status_code == 403, patched.text
