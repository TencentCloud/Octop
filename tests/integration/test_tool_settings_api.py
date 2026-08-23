"""Integration tests for GET/PUT /api/agents/{id}/tool-settings."""

from __future__ import annotations

from typing import Any


async def test_tool_settings_list_and_put(env: Any) -> None:
    client, srv, auth = env
    created = await client.post(
        "/api/agents",
        headers=auth,
        json={"name": "tool-settings-agent"},
    )
    assert created.status_code == 201, created.text
    aid = created.json()["agent_id"]

    listed = await client.get(f"/api/agents/{aid}/tool-settings", headers=auth)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    tools = body["tools"]
    assert any(t["name"] == "web_fetch" and t["source"] == "builtin" for t in tools)
    assert any(t["name"] == "read_file" and t["disableable"] is False for t in tools)
    assert any(t["name"] == "execute" and t["disableable"] is True for t in tools)

    put = await client.put(
        f"/api/agents/{aid}/tool-settings",
        headers=auth,
        json={"disabled_builtin": ["web_fetch", "execute", "read_file"]},
    )
    assert put.status_code == 200, put.text
    put_body = put.json()
    by_name = {t["name"]: t for t in put_body["tools"] if t["source"] == "builtin"}
    assert by_name["web_fetch"]["enabled"] is False
    assert by_name["execute"]["enabled"] is False
    assert by_name["read_file"]["enabled"] is True  # critical; ignore disable

    cfg = srv.app_runtime.agent_registry.get_config(aid)
    assert cfg.get("tools_disabled") == ["execute", "web_fetch"]


async def test_tool_settings_patch_builtin_and_plugin(env: Any) -> None:
    client, srv, auth = env
    created = await client.post(
        "/api/agents",
        headers=auth,
        json={"name": "tool-patch-agent"},
    )
    assert created.status_code == 201, created.text
    aid = created.json()["agent_id"]

    r = await client.patch(
        f"/api/agents/{aid}/tool-settings/web_fetch",
        headers=auth,
        json={"enabled": False, "source": "builtin"},
    )
    assert r.status_code == 200, r.text
    by_name = {t["name"]: t for t in r.json()["tools"] if t["source"] == "builtin"}
    assert by_name["web_fetch"]["enabled"] is False
    cfg = srv.app_runtime.agent_registry.get_config(aid)
    assert "web_fetch" in set(cfg.get("tools_disabled") or [])

    # Critical tool cannot be disabled.
    bad = await client.patch(
        f"/api/agents/{aid}/tool-settings/read_file",
        headers=auth,
        json={"enabled": False, "source": "builtin"},
    )
    assert bad.status_code == 400, bad.text
