"""HTTP contracts for login captcha and admin settings."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

import pytest

from octop.infra.auth.captcha import set_test_siteverify_url
from octop.infra.auth.captcha.store import SETTINGS_KEY
from octop.infra.auth.sso.crypto import encrypt_secret
from tests.support.auth import bootstrap_admin


class _Siteverify(BaseHTTPRequestHandler):
    payload: dict[str, object] = {"success": True}
    hits: int = 0

    def _reply(self) -> None:
        type(self).hits += 1
        raw = json.dumps(self.payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        self._reply()

    def do_GET(self) -> None:
        self._reply()

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@pytest.fixture
def siteverify() -> tuple[str, type[_Siteverify]]:
    _Siteverify.payload = {"success": True}
    _Siteverify.hits = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Siteverify)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/siteverify"
    yield url, _Siteverify
    server.shutdown()
    server.server_close()
    set_test_siteverify_url("turnstile", None)
    set_test_siteverify_url("tencent", None)


@pytest.fixture
async def client(app_client: Any) -> Any:
    yield app_client


def _enable_turnstile(srv: Any, *, site_key: str = "0xsite", secret: str = "test-secret") -> None:
    _enable_provider(srv, "turnstile", site_key=site_key, secret=secret)


def _enable_provider(
    srv: Any,
    slug: str,
    *,
    site_key: str,
    secret: str,
    cam_id: str = "",
    cam_key: str = "",
) -> None:
    row: dict[str, str] = {
        "site_key": site_key,
        "secret_enc": encrypt_secret(srv.services.secret_repo, secret).decode("ascii"),
    }
    if cam_id:
        row["cam_secret_id"] = cam_id
    if cam_key:
        row["cam_secret_enc"] = encrypt_secret(srv.services.secret_repo, cam_key).decode("ascii")
    srv.services.settings_repo.set(
        SETTINGS_KEY,
        json.dumps(
            {
                "active": slug,
                "providers": {slug: row},
            }
        ),
    )


async def test_login_without_token_still_works_on_slider(client: Any) -> None:
    c, _, home = client
    await bootstrap_admin(c, home, username="alice", password="TestPass12")
    r = await c.post("/api/auth/login", json={"username": "alice", "password": "TestPass12"})
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_strong_login_requires_token_before_password(client: Any) -> None:
    c, srv, home = client
    await bootstrap_admin(c, home, username="alice", password="TestPass12")
    _enable_turnstile(srv)
    r = await c.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CAPTCHA_REQUIRED"
    row = srv.services.user_repo.get_by_username("alice")
    assert row is not None
    assert int(row.login_failed_count or 0) == 0


async def test_strong_login_mocked_ok_token_returns_jwt(client: Any, siteverify: Any) -> None:
    url, handler = siteverify
    set_test_siteverify_url("turnstile", url)
    handler.payload = {"success": True}
    c, srv, home = client
    await bootstrap_admin(c, home, username="alice", password="TestPass12")
    _enable_turnstile(srv)
    r = await c.post(
        "/api/auth/login",
        json={"username": "alice", "password": "TestPass12", "captcha_token": "ok-token"},
    )
    assert r.status_code == 200
    assert r.json()["access_token"]
    assert handler.hits == 1


async def test_captcha_fail_does_not_increment_lockout(client: Any, siteverify: Any) -> None:
    url, handler = siteverify
    set_test_siteverify_url("turnstile", url)
    handler.payload = {"success": False}
    c, srv, home = client
    await bootstrap_admin(c, home, username="alice", password="TestPass12")
    _enable_turnstile(srv)
    r = await c.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong", "captcha_token": "bad"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CAPTCHA_FAILED"
    row = srv.services.user_repo.get_by_username("alice")
    assert row is not None
    assert int(row.login_failed_count or 0) == 0


async def test_tencent_login_mocked_ok_returns_jwt(client: Any, siteverify: Any) -> None:
    url, handler = siteverify
    set_test_siteverify_url("tencent", url)
    handler.payload = {"Response": {"CaptchaCode": 1, "CaptchaMsg": "OK", "EvilLevel": 0}}
    c, srv, home = client
    await bootstrap_admin(c, home, username="alice", password="TestPass12")
    _enable_provider(
        srv,
        "tencent",
        site_key="195642000",
        secret="app-secret",
        cam_id="AKIDcam",
        cam_key="camkey",
    )
    pub = await c.get("/api/auth/captcha")
    assert pub.json() == {"provider": "tencent", "site_key": "195642000"}
    r = await c.post(
        "/api/auth/login",
        json={
            "username": "alice",
            "password": "TestPass12",
            "captcha_token": "tr03ticket:@rand",
        },
    )
    assert r.status_code == 200
    assert r.json()["access_token"]
    assert handler.hits == 1


async def test_tencent_login_without_cam_keys_fails(client: Any, siteverify: Any) -> None:
    url, handler = siteverify
    set_test_siteverify_url("tencent", url)
    handler.payload = {"Response": {"CaptchaCode": 1, "CaptchaMsg": "OK"}}
    c, srv, home = client
    await bootstrap_admin(c, home, username="alice", password="TestPass12")
    _enable_provider(srv, "tencent", site_key="195642000", secret="app-secret")
    r = await c.post(
        "/api/auth/login",
        json={
            "username": "alice",
            "password": "TestPass12",
            "captcha_token": "tr03ticket:@rand",
        },
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CAPTCHA_FAILED"
    assert handler.hits == 0


async def test_tencent_login_rejects_reused_ticket_code(client: Any, siteverify: Any) -> None:
    url, handler = siteverify
    set_test_siteverify_url("tencent", url)
    handler.payload = {"Response": {"CaptchaCode": 9, "CaptchaMsg": "ticket reused"}}
    c, srv, home = client
    await bootstrap_admin(c, home, username="alice", password="TestPass12")
    _enable_provider(
        srv,
        "tencent",
        site_key="195642000",
        secret="app-secret",
        cam_id="AKIDcam",
        cam_key="camkey",
    )
    r = await c.post(
        "/api/auth/login",
        json={
            "username": "alice",
            "password": "TestPass12",
            "captcha_token": "tr03ticket:@rand",
        },
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CAPTCHA_FAILED"
    assert handler.hits == 1


async def test_known_locked_user_skips_siteverify(client: Any, siteverify: Any) -> None:
    url, handler = siteverify
    set_test_siteverify_url("turnstile", url)
    handler.payload = {"success": True}
    c, srv, home = client
    await bootstrap_admin(c, home, username="alice", password="TestPass12")
    _enable_turnstile(srv)
    row = srv.services.user_repo.get_by_username("alice")
    assert row is not None
    srv.services.user_repo.record_failed_login(row.id, max_attempts=1, lockout_seconds=600)
    r = await c.post(
        "/api/auth/login",
        json={"username": "alice", "password": "TestPass12", "captcha_token": "ok-token"},
    )
    assert r.status_code == 429 or r.json()["error"]["code"] == "LOGIN_LOCKED"
    assert r.json()["error"]["code"] == "LOGIN_LOCKED"
    assert handler.hits == 0


async def test_overlong_captcha_token_is_422(client: Any) -> None:
    c, srv, home = client
    await bootstrap_admin(c, home, username="alice", password="TestPass12")
    _enable_turnstile(srv)
    r = await c.post(
        "/api/auth/login",
        json={
            "username": "alice",
            "password": "TestPass12",
            "captcha_token": "x" * 4097,
        },
    )
    assert r.status_code == 422


async def test_admin_captcha_get_put_and_null_delete(env: Any) -> None:
    c, _srv, auth = env
    r = await c.get("/api/settings/captcha", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["active"] == "slider"
    assert body["available"] == [
        "slider",
        "tencent",
        "turnstile",
        "hcaptcha",
        "recaptcha-v3",
    ]
    assert body["source"] in {"settings", "env"}
    assert body["v3_min_score"] == 0.5
    assert "secret" not in str(body)
    assert "secret_enc" not in str(body)

    r = await c.put(
        "/api/settings/captcha",
        headers=auth,
        json={"active": "turnstile"},
    )
    assert r.status_code == 400
    after = await c.get("/api/settings/captcha", headers=auth)
    assert after.json()["active"] == "slider"

    r = await c.put(
        "/api/settings/captcha",
        headers=auth,
        json={
            "active": "turnstile",
            "providers": {"turnstile": {"site_key": "0xsite", "secret": "s3cret"}},
        },
    )
    assert r.status_code == 200
    saved = r.json()
    assert saved["active"] == "turnstile"
    assert saved["providers"]["turnstile"] == {
        "site_key": "0xsite",
        "has_secret": True,
        "cam_secret_id": "",
        "has_cam_secret": False,
    }
    assert "s3cret" not in str(saved)
    assert "secret_enc" not in str(saved)

    r = await c.put(
        "/api/settings/captcha",
        headers=auth,
        json={
            "providers": {
                "tencent": {
                    "site_key": "195642000",
                    "secret": "app-secret",
                    "cam_secret_id": "AKIDcam",
                    "cam_secret": "camkey",
                }
            },
        },
    )
    assert r.status_code == 200
    tencent_view = r.json()["providers"]["tencent"]
    assert tencent_view["cam_secret_id"] == "AKIDcam"
    assert tencent_view["has_cam_secret"] is True
    assert "camkey" not in str(r.json())

    pub = await c.get("/api/auth/captcha")
    assert pub.json() == {"provider": "turnstile", "site_key": "0xsite"}

    r = await c.put(
        "/api/settings/captcha",
        headers=auth,
        json={"providers": {"turnstile": None}, "active": "slider"},
    )
    assert r.status_code == 200
    assert "turnstile" not in r.json()["providers"]
    pub = await c.get("/api/auth/captcha")
    assert pub.json() == {"provider": "slider"}


async def test_admin_captcha_forbidden_without_permission(env: Any) -> None:
    c, _srv, admin_auth = env
    await c.post(
        "/api/users",
        headers=admin_auth,
        json={"username": "bob", "password": "TestPass12", "role": "user"},
    )
    bob_tok = (
        await c.post("/api/auth/login", json={"username": "bob", "password": "TestPass12"})
    ).json()["access_token"]
    r = await c.get("/api/settings/captcha", headers={"Authorization": f"Bearer {bob_tok}"})
    assert r.status_code == 403
