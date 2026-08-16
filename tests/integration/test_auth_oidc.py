"""OIDC HTTP route integration tests."""

from __future__ import annotations

from typing import Any

import pytest

from octop.infra.auth.sso.service import RedirectResult, SsoService
from tests.support.auth import bearer, bootstrap_admin, login


@pytest.fixture
async def client(app_client):
    yield app_client


async def test_oidc_public_routes_and_exchange_return_login_shape(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, srv, home = client
    await bootstrap_admin(c, home)
    assert srv.user_manager is not None
    user = srv.user_manager.get("admin")
    assert user is not None

    monkeypatch.setattr(
        SsoService,
        "start_login",
        lambda self, *, redirect_after, public_base: {
            "authorization_url": (
                f"https://idp.example/authorize?redirect={redirect_after}&state=browser-state"
            ),
            "state": "browser-state",
        },
    )

    callback_states: list[str | None] = []

    async def callback(self: SsoService, **_: Any) -> RedirectResult:
        callback_states.append(_["state"])
        return RedirectResult("http://testserver/login/oidc/complete#code=one-time")

    async def exchange(self: SsoService, code: str):
        assert code == "one-time"
        return user

    monkeypatch.setattr(SsoService, "handle_callback", callback)
    monkeypatch.setattr(SsoService, "exchange_login_code", exchange)

    status = await c.get("/api/auth/oidc/status")
    assert status.status_code == 200
    assert status.json() == {"enabled": False, "display_name": ""}

    start = await c.post("/api/auth/oidc/start", json={"redirect_after": "/chat"})
    assert start.status_code == 200
    assert "redirect=/chat" in start.json()["authorization_url"]
    assert start.cookies["octop_oidc_state"] == "browser-state"
    set_cookie = start.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "Max-Age=600" in set_cookie
    assert "Path=/api/auth/oidc" in set_cookie
    assert "SameSite=lax" in set_cookie

    callback_response = await c.get(
        "/api/auth/oidc/callback", params={"code": "provider-code", "state": "attacker-state"}
    )
    assert callback_response.status_code == 302
    assert callback_response.headers["location"] == "http://testserver/login?oidc_error=state"
    assert callback_states == []
    assert "octop_oidc_state=" in callback_response.headers["set-cookie"]
    assert "Max-Age=0" in callback_response.headers["set-cookie"]

    start = await c.post("/api/auth/oidc/start", json={"redirect_after": "/chat"})
    callback_response = await c.get(
        "/api/auth/oidc/callback", params={"code": "provider-code", "state": "browser-state"}
    )
    assert callback_response.status_code == 302
    assert callback_response.headers["location"].endswith("#code=one-time")
    assert callback_states == ["browser-state"]

    exchange_response = await c.post("/api/auth/oidc/exchange", json={"code": "one-time"})
    assert exchange_response.status_code == 200
    body = exchange_response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == srv.services.config.access_token_ttl_seconds
    assert body["user"]["username"] == "admin"
    assert body["access_token"]


async def test_oidc_config_requires_admin_and_returns_public_callback_url(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, _srv, home = client
    await bootstrap_admin(c, home)
    token = await login(c)

    assert (await c.get("/api/auth/oidc/config")).status_code == 401

    config = await c.get("/api/auth/oidc/config", headers=bearer(token))
    assert config.status_code == 200
    assert config.json()["redirect_uri"] == "http://testserver/api/auth/oidc/callback"

    update = await c.put(
        "/api/auth/oidc/config",
        headers=bearer(token),
        json={
            "enabled": False,
            "display_name": "Company Login",
            "issuer": "https://issuer.example",
            "client_id": "octop-client",
            "dashboard_origin": "https://dashboard.example",
        },
    )
    assert update.status_code == 200
    assert update.json()["display_name"] == "Company Login"
    assert update.json()["redirect_uri"] == "http://testserver/api/auth/oidc/callback"
    assert "client_secret" not in update.json()

    config = await c.get(
        "/api/auth/oidc/config",
        headers={**bearer(token), "X-Forwarded-Proto": "https", "X-Forwarded-Host": "api.example"},
    )
    assert config.status_code == 200
    assert config.json()["dashboard_origin"] == "https://dashboard.example"
    assert config.json()["redirect_uri"] == "https://api.example/api/auth/oidc/callback"

    monkeypatch.setattr(
        SsoService, "test_connection", lambda self: {"ok": True, "detail": "reachable"}
    )
    tested = await c.post("/api/auth/oidc/config/test", headers=bearer(token))
    assert tested.status_code == 200
    assert tested.json() == {"ok": True, "detail": "reachable"}
