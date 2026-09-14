"""OAuth SSO HTTP route integration tests."""

from __future__ import annotations

from typing import Any

import pytest

from octop.infra.auth.sso.service import RedirectResult, SsoService
from tests.support.auth import bearer, bootstrap_admin, login


@pytest.fixture
async def client(app_client):
    yield app_client


async def test_oauth_public_routes_and_oidc_kind_share_redirect(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, srv, home = client
    await bootstrap_admin(c, home)
    assert srv.user_manager is not None
    user = srv.user_manager.get("admin")
    assert user is not None

    monkeypatch.setattr(
        SsoService,
        "start_login_for_kind",
        lambda self, kind, *, redirect_after, public_base, bind_user_id=None: {
            "authorization_url": (
                "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
                f"?kind={kind}&redirect={redirect_after}&state=browser-state"
            ),
            "state": "browser-state",
        },
    )

    async def callback(self: SsoService, **_: Any) -> RedirectResult:
        return RedirectResult("http://testserver/login/oidc/complete#code=one-time")

    async def exchange(self: SsoService, code: str):
        assert code == "one-time"
        return user

    monkeypatch.setattr(SsoService, "handle_callback", callback)
    monkeypatch.setattr(SsoService, "exchange_login_code", exchange)

    status = await c.get("/api/auth/oauth/status")
    assert status.status_code == 200
    kinds = {item["kind"] for item in status.json()["providers"]}
    assert kinds == {"oidc", "feishu"}

    start = await c.post("/api/auth/oauth/start", json={"kind": "oidc", "redirect_after": "/chat"})
    assert start.status_code == 200
    assert start.cookies["octop_sso_state"] == "browser-state"
    assert "Path=/api/auth" in start.headers["set-cookie"]

    callback_response = await c.get(
        "/api/auth/oauth/callback", params={"code": "provider-code", "state": "browser-state"}
    )
    assert callback_response.status_code == 302
    assert callback_response.headers["location"].endswith("#code=one-time")

    via_oidc = await c.post("/api/auth/oidc/exchange", json={"code": "one-time"})
    assert via_oidc.status_code == 200
    assert via_oidc.json()["user"]["username"] == "admin"


async def test_oauth_bind_requires_auth_and_providers_are_not_public(client) -> None:
    c, _srv, home = client
    await bootstrap_admin(c, home)
    assert (await c.post("/api/auth/oauth/bind/start", json={"kind": "feishu"})).status_code == 401
    assert (await c.get("/api/auth/oauth/providers/feishu")).status_code == 401
    token = await login(c)
    started = await c.post(
        "/api/auth/oauth/bind/start",
        headers=bearer(token),
        json={"kind": "feishu"},
    )
    # Provider is not configured, so start is a 400 — but it is authenticated.
    assert started.status_code == 400

    config = await c.get("/api/auth/oauth/providers/feishu", headers=bearer(token))
    assert config.status_code == 200
    assert config.json()["kind"] == "feishu"
    assert config.json()["redirect_uri"].endswith("/api/auth/oauth/callback")
    assert "client_secret" not in config.json()
