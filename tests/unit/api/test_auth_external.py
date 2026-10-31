"""受信外部系统免登接口（/api/auth/external/exchange）单元测试。

覆盖：未配置/未启用/缺少密钥 401（不泄露原因）、签名/app_id/时间窗/nonce 重放 401、
正确签名换一次性登录码再经 /api/auth/oidc/exchange 开户并写审计、登录码不可重放、
未来时间戳窗口结束后 nonce 仍不可重放、控制字符 422、同一用户重复登录复用账号、
禁用用户 403、匿名失败节流 429，以及 oauth/start 与 oauth/status 的 external 回归。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import AsyncIterator, Iterator
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
OIDC_EXCHANGE_URL = "/api/auth/oidc/exchange"


def _sign(app_id: str, username: str, timestamp: int, nonce: str) -> str:
    """按约定明文计算 HMAC-SHA256 签名（与外部系统侧算法一致）。"""
    message = f"{app_id}\n{username}\n{timestamp}\n{nonce}"
    return hmac.new(SECRET.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _payload(username: str, **overrides: object) -> dict[str, object]:
    """构造合法换票请求体；overrides 可覆盖任意字段以构造异常场景。"""
    timestamp = int(overrides.pop("timestamp", int(time.time())))  # type: ignore[arg-type]
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


async def _exchange_code(c: httpx.AsyncClient, login_code: str) -> httpx.Response:
    """用一次性登录码换 JWT（与交接页调用的既有接口相同）。"""
    return await c.post(OIDC_EXCHANGE_URL, json={"code": login_code})


def _assert_login_code(data: dict[str, object]) -> str:
    """成功体只有一次性码和 60 秒有效期，不得直接下发 JWT。"""
    assert "access_token" not in data
    assert data["expires_in"] == 60
    login_code = data["login_code"]
    assert isinstance(login_code, str) and login_code
    return login_code


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, int]]:
    """同时钉住 time.time 与 sso 仓储的 now_ts（delete_expired 用后者）。"""
    clock = {"now": 1_700_000_000}

    def _now() -> float:
        return float(clock["now"])

    monkeypatch.setattr(time, "time", _now)
    monkeypatch.setattr("octop.infra.db.repos.sso.now_ts", lambda: int(clock["now"]))
    yield clock


async def test_exchange_rejects_when_provider_not_configured(client) -> None:
    """未配置 external provider 时对外统一 401 AUTH_FAILED，不泄露配置状态。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    r = await c.post(EXCHANGE_URL, json=_payload("member01"))
    assert r.status_code == 401
    body = r.json()["error"]
    assert body["code"] == "AUTH_FAILED"
    assert "disabled" not in body["message"].lower()
    audits = srv.services.audit_repo.query(action="auth.external_failed")
    assert [(a.actor, a.payload) for a in audits] == [("member01", "disabled")]


async def test_exchange_rejects_when_provider_disabled(client) -> None:
    """已配置但 enabled=False 时对外统一 401 AUTH_FAILED。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv, enabled=False)
    r = await c.post(EXCHANGE_URL, json=_payload("member01"))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"


async def test_exchange_success_creates_user_and_writes_audit(client) -> None:
    """正确签名返回一次性登录码；换码后开户并写 auth.external_login 审计。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    r = await c.post(
        EXCHANGE_URL,
        json=_payload("member01", display_name="成员一号", email="member01@example.com"),
    )
    assert r.status_code == 200
    login_code = _assert_login_code(r.json())
    exchanged = await _exchange_code(c, login_code)
    assert exchanged.status_code == 200
    data = exchanged.json()
    assert data["access_token"]
    assert data["token_type"] == "Bearer"
    assert data["user"]["username"] == "member01"
    # 自动开户使用默认角色
    assert data["user"]["role"] == "user"
    row = srv.services.user_repo.get_by_username("member01")
    assert row is not None
    assert row.id == data["user"]["id"]
    audits = srv.services.audit_repo.query(action="auth.external_login")
    assert [(a.actor, a.target) for a in audits] == [("member01", "member01")]
    # 同一登录码不可再次换票
    replay = await _exchange_code(c, login_code)
    assert replay.status_code >= 400
    assert replay.status_code < 500


async def test_exchange_rejects_bad_signature_and_writes_failure_audit(client) -> None:
    """签名错误返回 401 AUTH_FAILED，审计只记稳定原因码，响应不带具体原因。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    r = await c.post(EXCHANGE_URL, json=_payload("member02", signature="0" * 64))
    assert r.status_code == 401
    body = r.json()["error"]
    assert body["code"] == "AUTH_FAILED"
    assert "signature" not in body["message"].lower()
    audits = srv.services.audit_repo.query(action="auth.external_failed")
    assert [(a.actor, a.target, a.payload) for a in audits] == [
        ("member02", "member02", "bad_signature")
    ]


async def test_exchange_rejects_wrong_app_id(client) -> None:
    """app_id 与配置不一致返回 401，审计原因为 bad_app_id。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    r = await c.post(EXCHANGE_URL, json=_payload("member03", app_id="other-app"))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"
    audits = srv.services.audit_repo.query(action="auth.external_failed")
    assert audits[0].payload == "bad_app_id"


async def test_exchange_rejects_stale_timestamp(client) -> None:
    """时间戳超出 ±300 秒窗口返回 401。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    r = await c.post(EXCHANGE_URL, json=_payload("member04", timestamp=int(time.time()) - 1000))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"
    audits = srv.services.audit_repo.query(action="auth.external_failed")
    assert audits[0].payload == "stale_timestamp"


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


async def test_exchange_rejects_replay_after_future_timestamp_window(
    client, frozen_clock: dict[str, int]
) -> None:
    """未来时间戳在窗口最后一秒（abs(t-timestamp)==300）仍不可重放。

    nonce 占位行必须活过时间窗：``delete_expired`` 用 ``expires_at <= now``。
    若过期被改成 ``max(now, timestamp)+300``，本用例会在窗口尚未结束时删行并放行重放。
    """
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    # 起点 1_700_000_000；请求时间戳落在未来偏差上沿 start+300
    timestamp = frozen_clock["now"] + 300
    body = _payload("member-future", timestamp=timestamp, nonce="nonce-future-01")
    first = await c.post(EXCHANGE_URL, json=body)
    assert first.status_code == 200
    _assert_login_code(first.json())
    with srv.services.db.connect() as conn:
        row = conn.execute(
            "SELECT expires_at FROM sso_login_states WHERE state = ?",
            ("nonce-future-01",),
        ).fetchone()
    assert row is not None
    assert int(row["expires_at"]) == timestamp + 301
    # 推进到 timestamp+300（相对起点 +600）：仍在 ±300 窗口内，占位行不得被清掉
    frozen_clock["now"] = timestamp + 300
    replay = await c.post(EXCHANGE_URL, json=body)
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "AUTH_FAILED"
    assert "nonce" not in replay.json()["error"]["message"].lower()


async def test_exchange_rejects_newline_in_signed_fields(client) -> None:
    """用户名或 nonce 含换行时由请求体 pattern 拒绝（422），且不开户。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    username = "member\nadmin"
    bad_user = await c.post(EXCHANGE_URL, json=_payload(username))
    assert bad_user.status_code == 422
    bad_nonce = await c.post(EXCHANGE_URL, json=_payload("member-nl", nonce="nonce\nreplay"))
    assert bad_nonce.status_code == 422
    assert srv.services.user_repo.get_by_username(username) is None
    assert srv.services.user_repo.get_by_username("member-nl") is None


async def test_exchange_reuses_existing_user_for_same_username(client) -> None:
    """同一 username 换不同 nonce 两次登录均 200，且换码后复用同一账号。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    first = await c.post(EXCHANGE_URL, json=_payload("member06"))
    second = await c.post(EXCHANGE_URL, json=_payload("member06"))
    assert first.status_code == 200
    assert second.status_code == 200
    first_user = (await _exchange_code(c, _assert_login_code(first.json()))).json()["user"]
    second_user = (await _exchange_code(c, _assert_login_code(second.json()))).json()["user"]
    assert first_user["id"] == second_user["id"]
    # 复用登录不重复开户
    creates = srv.services.audit_repo.query(action="user.sso_create")
    assert [(a.actor, a.target) for a in creates] == [("member06", "member06")]


async def test_exchange_rejects_when_secret_missing(client) -> None:
    """已配置 client_id 但未设置共享密钥时对外统一 401。

    密钥缺失被 ``is_configured`` 视为未启用（ValueError: disabled），不进入验签。
    """
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
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"
    audits = srv.services.audit_repo.query(action="auth.external_failed")
    assert audits[0].payload == "disabled"


async def test_exchange_accepts_uppercase_hex_signature(client) -> None:
    """签名以大写 hex 提交时服务端归一化后验签通过，换码得到对应用户。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    body = _payload("member08")
    body["signature"] = str(body["signature"]).upper()
    r = await c.post(EXCHANGE_URL, json=body)
    assert r.status_code == 200
    exchanged = await _exchange_code(c, _assert_login_code(r.json()))
    assert exchanged.status_code == 200
    assert exchanged.json()["user"]["username"] == "member08"


async def test_exchange_rejects_disabled_user(client) -> None:
    """开户成功后经管理路径禁用该用户，再次换票透传 USER_DISABLED（403）。"""
    c, srv, home = client
    await bootstrap_admin(c, home)
    _configure_external(srv)
    first = await c.post(EXCHANGE_URL, json=_payload("member09"))
    assert first.status_code == 200
    opened = await _exchange_code(c, _assert_login_code(first.json()))
    assert opened.status_code == 200
    assert opened.json()["user"]["username"] == "member09"
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
