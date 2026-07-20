"""tests/integration/test_setup_bootstrap.py — initial-admin path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from octop.infra.server import OctopServer
from octop.infra.setup.password_file import read_password
from tests.support.app import write_octop_config
from tests.support.auth import auth_header, bootstrap_admin


async def test_setup_status_flips_after_bootstrap(patched_app_client: Any) -> None:
    c, _srv, home = patched_app_client
    r = await c.get("/api/setup/status")
    assert r.status_code == 200
    assert r.json()["setup_required"] is True

    r = await bootstrap_admin(c, home)
    assert r.status_code == 201

    r = await c.get("/api/setup/status")
    assert r.json()["setup_required"] is False


async def test_bootstrap_creates_default_main_agent(patched_app_client: Any) -> None:
    c, _srv, home = patched_app_client
    await bootstrap_admin(c, home)
    auth = await auth_header(c)

    r = await c.get("/api/agents", headers=auth)
    assert r.status_code == 200
    agents = r.json()
    assert len(agents) == 1
    assert agents[0]["agent_id"] == "main"
    assert agents[0]["name"] == "小通 · 通用助手"
    assert agents[0]["state"] in {"created", "idle", "stopped", "failed", "running", "unknown"}


async def test_main_not_created_until_finish(patched_app_client: Any) -> None:
    c, _srv, home = patched_app_client
    pw = read_password(home.parent)
    assert pw is not None
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    admin = (
        await c.post(
            "/api/setup/initial-admin",
            json={"username": "admin", "password": "pw"},
            headers={"Authorization": f"Bearer {tok}"},
        )
    ).json()
    auth = {"Authorization": f"Bearer {admin['access_token']}"}
    r = await c.get("/api/agents", headers=auth)
    assert r.status_code == 200
    assert r.json() == []

    finish = await c.post(
        "/api/setup/finish",
        json={"provider_draft": None},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert finish.status_code == 200
    r = await c.get("/api/agents", headers=auth)
    assert len(r.json()) == 1
    assert r.json()[0]["agent_id"] == "main"


async def test_double_bootstrap_returns_410(patched_app_client: Any) -> None:
    c, _srv, home = patched_app_client
    r = await bootstrap_admin(c, home)
    assert r.status_code == 201
    r = await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin2", "password": "pw"},
    )
    assert r.status_code == 410
    assert r.json()["error"]["code"] == "SETUP_REQUIRED"


async def test_start_writes_wizard_password_when_no_users(tmp_octop_home: Path) -> None:
    srv = OctopServer(home=tmp_octop_home)
    await srv.start()
    try:
        assert (tmp_octop_home.parent / "octop-login.txt").exists()
    finally:
        await srv.stop()


async def test_start_skips_wizard_password_when_disabled(tmp_octop_home: Path) -> None:
    write_octop_config(tmp_octop_home, require_setup_password=False)
    srv = OctopServer(home=tmp_octop_home)
    await srv.start()
    try:
        assert not (tmp_octop_home / "octop-login.txt").exists()
    finally:
        await srv.stop()


async def test_main_agent_seeds_general_assistant_workspace(patched_app_client: Any) -> None:
    """Finish creates main with expert files even when no provider is configured yet."""
    c, _srv, home = patched_app_client
    await bootstrap_admin(c, home)
    ws = home / "agents" / "main"
    assert (ws / "SOUL.md").is_file()
    assert (ws / "skills" / "octop-assistant" / "SKILL.md").is_file()


async def test_main_agent_config_has_no_workspace_scoped_backend(patched_app_client: Any) -> None:
    """Default main must use harness DEFAULT_BACKEND_SPEC (no virtual root = workspace_dir)."""
    c, srv, home = patched_app_client
    await bootstrap_admin(c, home)
    assert srv.app_runtime is not None
    row = srv.app_runtime.agent_registry.get_row("main")
    assert row is not None
    cfg = json.loads(row.config_json or "{}")
    assert cfg.get("backend") is None
    ws = home / "agents" / "main"
    nested = list(ws.glob("Users")) + list(ws.glob("private"))
    assert not nested, f"unexpected nested workspace under main: {nested}"


async def test_main_agent_uses_general_assistant_template(patched_app_client: Any) -> None:
    c, _srv, home = patched_app_client
    await bootstrap_admin(c, home)
    auth = await auth_header(c)
    r = await c.get("/api/agents", headers=auth)
    assert r.status_code == 200
    agent = r.json()[0]
    assert agent["agent_id"] == "main"
    assert agent["name"] == "小通 · 通用助手"
    assert (
        agent.get("template_name") == "general-assistant"
        or (agent.get("config") or {}).get("expert_id") == "general-assistant"
    )
