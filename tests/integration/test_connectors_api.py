"""Integration tests for connector APIs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from octop.infra.connectors.custom_mcp import CUSTOM_MCP_KIND
from octop.infra.connectors.oauth.registry import save_oauth_ctx
from octop.infra.utils.ulid import new_ulid
from tests.support.app import octop_client, write_octop_config
from tests.support.auth import auth_header, bootstrap_admin, create_user, resolve_user_id
from tests.support.http import ws_chat_turn


@pytest.fixture
async def env(env_with_agent):
    yield env_with_agent


async def test_catalog(env):
    c, _, auth, _ = env
    r = await c.get("/api/connectors/catalog", headers=auth)
    assert r.status_code == 200
    kinds = {e["kind"] for e in r.json()}
    assert "tencent-docs" in kinds
    assert "notion" in kinds
    assert "figma" not in kinds
    assert "baidu-netdisk" not in kinds
    for kind in (
        "tencent-meeting",
        "tencent-lexiang",
        "notion",
        "tencent-news",
        "wechat-reading",
        "tencent-ardot",
        "dida365",
        "youdao-note",
        "tencent-weiyun",
        "qq-music",
        "fliggy",
        "baidu-map",
        "ctrip-wendao",
        "meituan-travel",
        "yuandian",
    ):
        entry = next(e for e in r.json() if e["kind"] == kind)
        assert entry["phase"] == "available", kind
    docs = next(e for e in r.json() if e["kind"] == "tencent-docs")
    assert docs.get("color")
    assert docs.get("quick_auth_url")
    assert "tools" not in docs
    weiyun = next(e for e in r.json() if e["kind"] == "tencent-weiyun")
    assert weiyun["auth_kind"] == "personal_token"
    assert weiyun["mcp_mode"] == "remote"
    assert weiyun.get("quick_auth_url") == "https://www.weiyun.com/act/openclaw"


async def test_create_tencent_instance(env):
    c, _, auth, _ = env
    r = await c.post(
        "/api/connector-instances",
        headers=auth,
        json={
            "kind": "tencent-docs",
            "display_name": "我的文档",
            "credentials": {"token": "test-token"},
        },
    )
    assert r.status_code == 201
    inst = r.json()
    assert inst["kind"] == "tencent-docs"
    assert inst["mcp_server_name"].startswith("tencent-docs__")
    assert inst.get("default_open") is False


async def test_create_instance_default_open(env):
    c, _, auth, _ = env
    r = await c.post(
        "/api/connector-instances",
        headers=auth,
        json={
            "kind": "tencent-docs",
            "display_name": "我的文档",
            "credentials": {"token": "test-token"},
            "default_open": True,
        },
    )
    assert r.status_code == 201
    inst = r.json()
    assert inst["default_open"] is True

    listed = await c.get("/api/connector-instances", headers=auth)
    assert listed.status_code == 200
    row = next(i for i in listed.json() if i["instance_id"] == inst["instance_id"])
    assert row["default_open"] is True

    detail = await c.get(f"/api/connector-instances/{inst['instance_id']}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["config"]["default_open"] is True
    assert detail.json()["default_open"] is True


async def test_chat_accepts_user_instance_mcp(env):
    c, _, auth, agent_id = env
    r = await c.post(
        "/api/connector-instances",
        headers=auth,
        json={
            "kind": "qq-mail",
            "display_name": "邮箱",
            "credentials": {"email": "a@qq.com", "password": "code"},
        },
    )
    assert r.status_code == 201
    mcp_name = r.json()["mcp_server_name"]

    chunks = await ws_chat_turn(c, agent_id, auth, mcp_servers=[mcp_name])
    assert chunks[-1].get("type") == "done"


async def test_chat_rejects_unknown_mcp(env):
    c, _, auth, agent_id = env
    chunks = await ws_chat_turn(c, agent_id, auth, mcp_servers=["unknown__instance"])
    assert chunks[0].get("type") == "error"


async def test_get_instance_detail(env):
    c, _, auth, _ = env
    r = await c.post(
        "/api/connector-instances",
        headers=auth,
        json={
            "kind": "qq-mail",
            "display_name": "邮箱",
            "credentials": {"email": "a@qq.com", "password": "code"},
        },
    )
    inst = r.json()
    r2 = await c.get(f"/api/connector-instances/{inst['instance_id']}", headers=auth)
    assert r2.status_code == 200
    detail = r2.json()
    assert detail["display_name"] == "邮箱"
    assert detail["credentials_preview"]["email"] == "a@qq.com"
    assert detail["credentials_preview"]["password_configured"] is True


async def test_probe_returns_tools(env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.qq_mail.probe_credentials",
        lambda _creds: None,
    )
    c, _, auth, _ = env
    r = await c.post(
        "/api/connectors/test-credentials",
        headers=auth,
        json={
            "kind": "qq-mail",
            "credentials": {"email": "a@qq.com", "password": "code"},
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["tool_count"] == 3
    assert len(data["tools"]) == 3
    assert data["tools"][0]["name"]


async def test_internal_mcp_tools_list(env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.qq_mail.probe_credentials",
        lambda _creds: None,
    )
    c, _, auth, _ = env
    r = await c.post(
        "/api/connector-instances",
        headers=auth,
        json={
            "kind": "qq-mail",
            "display_name": "邮箱",
            "credentials": {"email": "a@qq.com", "password": "code"},
        },
    )
    inst = r.json()
    # Fetch internal token via test endpoint path — decrypt not exposed; use gateway test
    r2 = await c.post(f"/api/connector-instances/{inst['instance_id']}/test", headers=auth)
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["tool_count"] == 3
    assert len(r2.json()["tools"]) == 3


async def test_auth_info(env):
    c, _, auth, _ = env
    r = await c.get("/api/connectors/auth/wechat-reading/info", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["login_url"] is None
    assert data["authorize_url"] == "https://weread.qq.com/r/weread-skills"
    assert data["auth_hint"]


async def test_oauth_start_public_http_notion_error_is_actionable(tmp_octop_home: Path):
    write_octop_config(tmp_octop_home)
    async with octop_client(tmp_octop_home) as (c, _srv):
        await bootstrap_admin(c, tmp_octop_home)
        auth = await auth_header(c)
        mocked_start = AsyncMock()
        with patch("octop.api.routers.connectors.start_oauth_for_target", mocked_start):
            r = await c.post(
                "/api/connectors/oauth/notion/start",
                headers={**auth, "host": "58.87.70.170"},
                json={"redirect_after": "/connectors"},
            )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "CONNECTOR_OAUTH_HTTPS_REQUIRED"
    assert "Notion" in body["error"]["message"]
    assert "HTTPS" in body["error"]["message"]
    mocked_start.assert_not_awaited()


async def test_patch_instance_status(env):
    c, _, auth, _ = env
    r = await c.post(
        "/api/connector-instances",
        headers=auth,
        json={
            "kind": "tencent-docs",
            "display_name": "doc",
            "credentials": {"token": "tok"},
        },
    )
    inst = r.json()
    r2 = await c.patch(
        f"/api/connector-instances/{inst['instance_id']}",
        headers=auth,
        json={"status": "disabled"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "disabled"


async def test_catalog_cli_connectors_last(env):
    c, _, auth, _ = env
    r = await c.get("/api/connectors/catalog", headers=auth)
    assert r.status_code == 200
    kinds = [e["kind"] for e in r.json()]
    assert "feishu-cli" in kinds
    assert "wecom-cli" in kinds
    assert kinds[-2:] == ["feishu-cli", "wecom-cli"]


async def test_install_cli_forbidden_for_non_admin(env):
    c, _, admin_auth, _ = env
    user_auth = await create_user(c, admin_auth, username="cli_user", permissions=[])
    r = await c.post("/api/connectors/feishu-cli/install-cli", headers=user_auth)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


async def test_install_cli_admin_ok_mocked(env, monkeypatch: pytest.MonkeyPatch):
    c, _, auth, _ = env

    def _fake_install(kind: str) -> dict:
        return {
            "ok": True,
            "kind": kind,
            "installed": True,
            "already_installed": True,
            "binary": "lark-cli",
            "version": "0.0.0-test",
            "install_command": "npm install -g @larksuite/cli",
            "doc_url": "https://example.com",
            "guide_url": "https://example.com",
        }

    monkeypatch.setattr(
        "octop.api.routers.connectors.install_connector_cli",
        _fake_install,
    )
    r = await c.post("/api/connectors/feishu-cli/install-cli", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["already_installed"] is True


async def test_cli_status_available_to_non_admin(env, monkeypatch: pytest.MonkeyPatch):
    c, _, admin_auth, _ = env
    user_auth = await create_user(c, admin_auth, username="cli_status_user")
    monkeypatch.setattr(
        "octop.api.routers.connectors.cli_install_status",
        lambda kind: {
            "ok": True,
            "kind": kind,
            "installed": False,
            "binary": None,
            "version": None,
            "install_command": "npm install -g @larksuite/cli",
            "doc_url": "https://example.com",
            "guide_url": "https://example.com",
        },
    )
    r = await c.get("/api/connectors/feishu-cli/cli-status", headers=user_auth)
    assert r.status_code == 200
    assert r.json()["installed"] is False


async def test_patch_custom_mcp_server_default_open_only(env):
    c, _, auth, _ = env
    put = await c.put(
        "/api/connectors/custom-mcp",
        headers=auth,
        json={
            "servers": {
                "linear": {
                    "transport": "streamable_http",
                    "url": "https://mcp.linear.app/mcp",
                    "enabled": True,
                }
            }
        },
    )
    assert put.status_code == 200

    patch = await c.patch(
        "/api/connectors/custom-mcp/servers/linear",
        headers=auth,
        json={"default_open": True},
    )
    assert patch.status_code == 200
    servers = patch.json()["servers"]
    assert servers["linear"]["default_open"] is True
    assert servers["linear"]["enabled"] is True

    patch_off = await c.patch(
        "/api/connectors/custom-mcp/servers/linear",
        headers=auth,
        json={"default_open": False},
    )
    assert patch_off.status_code == 200
    assert "default_open" not in patch_off.json()["servers"]["linear"]


async def test_custom_mcp_oauth_callback_applies_tokens(env):
    c, srv, auth, _ = env
    user_id = await resolve_user_id(c, auth, "admin")

    put = await c.put(
        "/api/connectors/custom-mcp",
        headers=auth,
        json={
            "servers": {
                "my-oauth-mcp": {
                    "transport": "streamable_http",
                    "url": "https://mcp.example.com/mcp",
                    "enabled": False,
                }
            }
        },
    )
    assert put.status_code == 200

    oauth_state = "test-oauth-state-xyz"
    state_id = new_ulid()
    srv.services.repos.connector_repo.create_oauth_state(
        state_id=state_id,
        state=oauth_state,
        user_id=user_id,
        kind=CUSTOM_MCP_KIND,
        code_verifier="verifier123",
        redirect_after="/connectors",
    )
    save_oauth_ctx(
        srv.services.settings_repo,
        state_id,
        {
            "flow": "custom_mcp",
            "kind": CUSTOM_MCP_KIND,
            "server_name": "my-oauth-mcp",
            "issuer": "https://auth.example.com",
            "resource": "https://mcp.example.com/mcp",
            "client_id": "cid",
            "client_secret": None,
            "redirect_uri": "http://testserver/api/connectors/oauth/callback",
            "metadata": {
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
            },
        },
    )

    with patch(
        "octop.api.routers.connectors.exchange_oauth_code",
        new_callable=AsyncMock,
        return_value={
            "access_token": "new-access-token",
            "refresh_token": "refresh-tok",
            "expires_at": 9_999_999_999,
        },
    ):
        callback = await c.get(
            f"/api/connectors/oauth/callback?code=authcode&state={oauth_state}",
            follow_redirects=False,
        )
    assert callback.status_code == 200
    assert "octop:connector-oauth" in callback.text

    stored = await c.get("/api/connectors/custom-mcp", headers=auth)
    assert stored.status_code == 200
    assert stored.json()["servers"]["my-oauth-mcp"]["oauth"]["configured"] is True

    pending = await c.get(f"/api/connectors/oauth/pending/{state_id}", headers=auth)
    assert pending.status_code == 200
    body = pending.json()
    assert body["applied"] is True
    assert body["server_name"] == "my-oauth-mcp"


async def test_custom_mcp_oauth_start_unified(env):
    c, _, auth, _ = env
    put = await c.put(
        "/api/connectors/custom-mcp",
        headers=auth,
        json={
            "servers": {
                "oauth-srv": {
                    "transport": "streamable_http",
                    "url": "https://mcp.example.com/mcp",
                }
            }
        },
    )
    assert put.status_code == 200

    mocked_start = AsyncMock(
        return_value=(
            "https://auth.example.com/authorize?state=x",
            "verifier",
            {"flow": "custom_mcp"},
        )
    )
    with (
        patch("octop.api.routers.connectors._is_public_http_uri", return_value=False),
        patch("octop.api.routers.connectors.start_oauth_for_target", mocked_start),
    ):
        r = await c.post(
            "/api/connectors/oauth/start",
            headers=auth,
            json={
                "target": {"type": "custom_mcp", "server_name": "oauth-srv"},
                "redirect_after": "/connectors",
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert data["authorize_url"].startswith("https://auth.example.com/")
    assert data["state_id"]
    mocked_start.assert_awaited_once()
    call_kwargs = mocked_start.await_args.kwargs
    assert call_kwargs["target"] == {"type": "custom_mcp", "server_name": "oauth-srv"}
    assert call_kwargs["mcp_url"] == "https://mcp.example.com/mcp"
