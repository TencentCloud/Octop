"""Tests for the DingTalk dashboard SSO adapter."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import jwt
import pytest

from octop.config import OctopConfig
from octop.infra.auth.sso.crypto import encrypt_secret
from octop.infra.auth.sso.providers.dingtalk import DingTalkAdapter
from octop.infra.auth.sso.service import SsoService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.users.manager import UserManager
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def service(tmp_path):
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    return SsoService(services, UserManager(services))


def _dingtalk_row(service: SsoService):
    secret = encrypt_secret(service._services.secret_repo, "app-secret")
    return service._services.sso_repo.upsert_by_kind(
        "dingtalk",
        enabled=True,
        display_name="DingTalk",
        issuer="",
        client_id="dingxxx",
        client_secret_enc=secret,
        scopes="openid",
        dashboard_origin=None,
        extra={},
    )


def test_dingtalk_authorize_url(service: SsoService) -> None:
    adapter = DingTalkAdapter(service)
    row = _dingtalk_row(service)
    url = adapter.authorize_url(
        row=row,
        state="st",
        nonce="ignored",
        code_challenge="ignored",
        redirect_uri="https://octop.example/api/auth/oauth/callback",
    )
    assert url.startswith("https://login.dingtalk.com/oauth2/auth?")
    query = httpx.QueryParams(url.split("?", 1)[1])
    assert query["client_id"] == "dingxxx"
    assert query["response_type"] == "code"
    assert query["scope"] == "openid"
    assert query["prompt"] == "consent"
    assert query["state"] == "st"


def test_dingtalk_complete_login_uses_union_id(service: SsoService) -> None:
    adapter = DingTalkAdapter(service)
    row = _dingtalk_row(service)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/oauth2/userAccessToken"):
            body = json.loads(request.content)
            assert body["grantType"] == "authorization_code"
            assert body["code"] == "auth-code"
            return httpx.Response(200, json={"accessToken": "user-token"})
        assert request.url.path.endswith("/contact/users/me")
        assert request.headers["x-acs-dingtalk-access-token"] == "user-token"
        return httpx.Response(
            200,
            json={"unionId": "uid_union", "nick": "Ada", "email": "ada@example.com"},
        )

    real_client = httpx.Client

    def factory(*args: object, **kwargs: object) -> httpx.Client:
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    login_state = type("State", (), {"code_verifier": "n/a"})()
    with patch("octop.infra.auth.sso.service.httpx.Client", side_effect=factory):
        subject, claims = adapter.complete_login(
            "auth-code",
            row=row,
            login_state=login_state,  # type: ignore[arg-type]
            redirect_uri="https://octop.example/api/auth/oauth/callback",
        )

    assert subject == "uid_union"
    assert claims["name"] == "Ada"
    assert claims["email"] == "ada@example.com"
    assert requests[0].method == "POST"


def test_dingtalk_missing_subject_is_invalid_token(service: SsoService) -> None:
    adapter = DingTalkAdapter(service)
    row = _dingtalk_row(service)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/userAccessToken"):
            return httpx.Response(200, json={"accessToken": "t"})
        return httpx.Response(200, json={"nick": "Ada"})

    real_client = httpx.Client

    def factory(*args: object, **kwargs: object) -> httpx.Client:
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    login_state = type("State", (), {})()
    with (
        patch("octop.infra.auth.sso.service.httpx.Client", side_effect=factory),
        pytest.raises(jwt.InvalidTokenError),
    ):
        adapter.complete_login(
            "auth-code",
            row=row,
            login_state=login_state,  # type: ignore[arg-type]
            redirect_uri="https://octop.example/api/auth/oauth/callback",
        )
