"""Tests for the WeCom dashboard SSO adapter."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import jwt
import pytest

from octop.config import OctopConfig
from octop.infra.auth.sso.crypto import encrypt_secret
from octop.infra.auth.sso.providers.wecom import WeComAdapter
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


def _wecom_row(service: SsoService, *, agent_id: str = "1000002"):
    secret = encrypt_secret(service._services.secret_repo, "corp-secret")
    return service._services.sso_repo.upsert_by_kind(
        "wecom",
        enabled=True,
        display_name="WeCom",
        issuer="",
        client_id="wwcorp",
        client_secret_enc=secret,
        scopes="",
        dashboard_origin=None,
        extra={"agent_id": agent_id},
    )


def test_wecom_authorize_url_uses_wwlogin(service: SsoService) -> None:
    adapter = WeComAdapter(service)
    row = _wecom_row(service)
    url = adapter.authorize_url(
        row=row,
        state="st",
        nonce="ignored",
        code_challenge="ignored",
        redirect_uri="https://octop.example/api/auth/oauth/callback",
    )
    assert url.startswith("https://login.work.weixin.qq.com/wwlogin/sso/login?")
    query = httpx.QueryParams(url.split("?", 1)[1])
    assert query["login_type"] == "CorpApp"
    assert query["appid"] == "wwcorp"
    assert query["agentid"] == "1000002"
    assert query["state"] == "st"


def test_wecom_is_configured_requires_agent_id(service: SsoService) -> None:
    adapter = WeComAdapter(service)
    row = _wecom_row(service, agent_id="")
    assert not adapter.is_configured(row)
    row = _wecom_row(service)
    assert adapter.is_configured(row)


def test_wecom_complete_login_reads_userid(service: SsoService) -> None:
    adapter = WeComAdapter(service)
    row = _wecom_row(service)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cgi-bin/gettoken"):
            return httpx.Response(200, json={"errcode": 0, "access_token": "corp-token"})
        if request.url.path.endswith("/cgi-bin/auth/getuserinfo"):
            assert request.url.params["code"] == "auth-code"
            return httpx.Response(
                200,
                json={"errcode": 0, "userid": "zhangsan", "user_ticket": "ticket"},
            )
        if request.url.path.endswith("/cgi-bin/user/get"):
            return httpx.Response(
                200,
                json={"errcode": 0, "name": "Zhang San", "email": "zs@example.com"},
            )
        if request.url.path.endswith("/cgi-bin/auth/getuserdetail"):
            return httpx.Response(
                200,
                json={"errcode": 0, "biz_mail": "zs@corp.example.com"},
            )
        return httpx.Response(404, json={"errcode": 404, "errmsg": "missing"})

    real_client = httpx.Client

    def factory(*args: object, **kwargs: object) -> httpx.Client:
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    login_state = type("State", (), {})()
    with patch("octop.infra.auth.sso.service.httpx.Client", side_effect=factory):
        subject, claims = adapter.complete_login(
            "auth-code",
            row=row,
            login_state=login_state,  # type: ignore[arg-type]
            redirect_uri="https://octop.example/api/auth/oauth/callback",
        )

    assert subject == "zhangsan"
    assert claims["name"] == "Zhang San"
    assert claims["email"] == "zs@corp.example.com"


def test_wecom_missing_userid_is_invalid_token(service: SsoService) -> None:
    adapter = WeComAdapter(service)
    row = _wecom_row(service)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cgi-bin/gettoken"):
            return httpx.Response(200, json={"errcode": 0, "access_token": "corp-token"})
        return httpx.Response(200, json={"errcode": 0})

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
