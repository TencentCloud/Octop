"""Integration tests for connector APIs."""

from __future__ import annotations

import pytest

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
