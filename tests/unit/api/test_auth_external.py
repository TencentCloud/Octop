"""受信外部系统免登接口（/api/auth/external/exchange）单元测试。

覆盖：未配置/未启用/缺少密钥 400、签名/app_id/时间窗/nonce 重放 401、
正确签名（含大写 hex）200 自动开户并写审计、同一用户重复登录复用账号、
禁用用户 403、匿名失败节流 429，以及 oauth/start 与 oauth/status 的 external 回归。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from tests.support.app import ensure_control_plane_bound
from tests.support.auth import bootstrap_admin

from octop.api.app import build_app
from octop.infra.server import OctopServer

APP_ID = "crm-system"
SECRET = "shared-hmac-secret-001"
EXCHANGE_URL = "/api/auth/external/exchange"


def _sign(app_id: str, username: str, timestamp: int, nonce: str) -> str:
    """按约定明文计算 HMAC-SHA256 签名（与外部系统侧算法一致）。"""
    message = f"{app_id}\n{username}\n{timestamp}\n{nonce}"
    return hmac.new(SECRET.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _payload(username: str, **overrides: object) -> dict[str, object]:
    """构造合法换票请求体；overrides 可覆盖任意字段以构造异常场景。"""
    timestamp = int(overrides.pop("timestamp", int(time.time())))
    nonce = str(overrides.pop("nonce", secrets.token_urlsafe(16)))
    app_id = str(overrides.pop("app_id", APP_ID))
    body: dict[str, object] = {
        "app_id": app_id,
        "username": username,
        "timestamp": timestamp,
        "nonce": nonce,
        "signature": _sign(app_id, username, timestamp, nonce),
    }
    body.update(overrides)
    return body


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, Path]]:
    srv = OctopServer(home=tmp_path)
    await srv.start()
    await ensure_control_plane_bound(srv)
    app = build_app(srv)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c, srv, tmp_path
    await srv.stop()


def _configure_external(srv: OctopServer, *, enabled: bool = True) -> None:
    """写入 external provider 配置（client_id=app_id，client_secret=HMAC 共享密钥）。"""
    srv.sso_service.put_config_for_kind(
        "external",
        {
            "enabled": enabled,
            "display_name": "External SSO",
            "client_id": APP_ID,
            "client_secret": SECRET,
        },
    )


async def test_exchange_rejects_when_provider_not_configured(client) -> None:
    """未配置 external provider 时返回 400 OIDC_BAD_REQUEST。"""
    c, _srv, home = client
    await bootstrap_admin(c, home)
    r = await c.post(EXCHANGE_URL, json=_payload("member01"))
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "OIDC_BAD_REQUEST"


async def test_exchange_rejects_when_provider_disabled(client) -> None:
    """已配置但 enabled=False 时返回 400 OIDC_BAD_REQUEST。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv, enabled=False)
    r = await c.post(EXCHANGE_URL, json=_payload("member01"))
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "OIDC_BAD_REQUEST"


async def test_exchange_success_creates_user_and_writes_audit(client) -> None:
    """正确签名返回与 /api/auth/login 一致的响应，自动开户并写 auth.external_login 审计。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    r = await c.post(
        EXCHANGE_URL,
        json=_payload("member01", display_name="成员一号", email="member01@example.com"),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["access_token"]
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] > 0
    assert data["user"]["username"] == "member01"
    # 自动开户使用默认角色
    assert data["user"]["role"] == "user"
    row = srv.services.user_repo.get_by_username("member01")
    assert row is not None
    assert row.id == data["user"]["id"]
    audits = srv.services.audit_repo.query(action="auth.external_login")
    assert [(a.actor, a.target) for a in audits] == [("member01", "member01")]


async def test_exchange_rejects_bad_signature_and_writes_failure_audit(client) -> None:
    """签名错误返回 401 AUTH_FAILED，并写 auth.external_failed 审计。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    r = await c.post(EXCHANGE_URL, json=_payload("member02", signature="0" * 64))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"
    audits = srv.services.audit_repo.query(action="auth.external_failed")
    assert [(a.actor, a.target) for a in audits] == [("member02", "member02")]


async def test_exchange_rejects_wrong_app_id(client) -> None:
    """app_id 与配置不一致返回 401。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    r = await c.post(EXCHANGE_URL, json=_payload("member03", app_id="other-app"))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"


async def test_exchange_rejects_stale_timestamp(client) -> None:
    """时间戳超出 ±300 秒窗口返回 401。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    r = await c.post(EXCHANGE_URL, json=_payload("member04", timestamp=int(time.time()) - 1000))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"


async def test_exchange_rejects_nonce_replay(client) -> None:
    """同一 nonce 第二次请求（重放）返回 401。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    nonce = secrets.token_urlsafe(16)
    first = await c.post(EXCHANGE_URL, json=_payload("member05", nonce=nonce))
    assert first.status_code == 200
    replay = await c.post(EXCHANGE_URL, json=_payload("member05", nonce=nonce))
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "AUTH_FAILED"


async def test_exchange_reuses_existing_user_for_same_username(client) -> None:
    """同一 username 换不同 nonce 两次登录均 200，且复用同一账号（user.id 相同）。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    first = await c.post(EXCHANGE_URL, json=_payload("member06"))
    second = await c.post(EXCHANGE_URL, json=_payload("member06"))
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["user"]["id"] == second.json()["user"]["id"]
    # 复用登录不重复开户
    creates = srv.services.audit_repo.query(action="user.sso_create")
    assert [(a.actor, a.target) for a in creates] == [("member06", "member06")]


async def test_exchange_rejects_when_secret_missing(client) -> None:
    """已配置 client_id 但未设置共享密钥时按配置不完整处理，返回 400 OIDC_BAD_REQUEST。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    # 直接写一行无密钥的 external 配置（绕过 put_config 的密钥加密路径）
    srv.services.sso_repo.upsert_by_kind(
        "external",
        enabled=True,
        display_name="External SSO",
        issuer="",
        client_id=APP_ID,
        client_secret_enc=None,
        scopes="",
        dashboard_origin=None,
    )
    r = await c.post(EXCHANGE_URL, json=_payload("member07"))
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "OIDC_BAD_REQUEST"


async def test_exchange_accepts_uppercase_hex_signature(client) -> None:
    """签名以大写 hex 提交时服务端归一化后验签通过，返回 200。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    body = _payload("member08")
    body["signature"] = str(body["signature"]).upper()
    r = await c.post(EXCHANGE_URL, json=body)
    assert r.status_code == 200
    assert r.json()["user"]["username"] == "member08"


async def test_exchange_rejects_disabled_user(client) -> None:
    """开户成功后经管理路径禁用该用户，再次换票透传 USER_DISABLED（403）。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    first = await c.post(EXCHANGE_URL, json=_payload("member09"))
    assert first.status_code == 200
    assert srv.user_manager is not None
    await srv.user_manager.disable("member09")
    # 禁用后重试须使用新 nonce（旧 nonce 已消耗）
    r = await c.post(EXCHANGE_URL, json=_payload("member09"))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "USER_DISABLED"


async def test_exchange_throttled_after_repeated_bad_signatures(client) -> None:
    """同一 username 连续错误签名达到阈值后触发匿名节流，返回 429 LOGIN_LOCKED。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    # 阈值取自节流实现使用的配置（login_max_attempts，默认 5）
    max_attempts = srv.services.config.login_max_attempts
    for _ in range(max_attempts):
        r = await c.post(EXCHANGE_URL, json=_payload("brute01", signature="0" * 64))
        assert r.status_code == 401
    # 达到阈值后的下一次请求在进入 external_login 之前即被节流
    r = await c.post(EXCHANGE_URL, json=_payload("brute01", signature="0" * 64))
    assert r.status_code == 429
    body = r.json()["error"]
    assert body["code"] == "LOGIN_LOCKED"
    assert body["details"]["retry_after_seconds"] > 0


async def test_oauth_start_rejects_external_kind(client) -> None:
    """external 不支持浏览器授权跳转：POST /api/auth/oauth/start 返回 400。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    r = await c.post("/api/auth/oauth/start", json={"kind": "external"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "OIDC_BAD_REQUEST"


async def test_oauth_status_excludes_external(client) -> None:
    """登录页 providers 列表不含 external（它不进 SSO_KINDS，仅服务器间免登）。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    r = await c.get("/api/auth/oauth/status")
    assert r.status_code == 200
    kinds = {p["kind"] for p in r.json()["providers"]}
    assert kinds == {"oidc", "feishu", "dingtalk", "wecom"}
