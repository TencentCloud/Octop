"""Tests for the Feishu dashboard SSO adapter."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import jwt
import pytest

from octop.config import OctopConfig
from octop.infra.auth.sso.crypto import encrypt_secret
from octop.infra.auth.sso.providers.feishu import FeishuAdapter
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


def _feishu_row(service: SsoService, *, region: str = "feishu"):
    secret = encrypt_secret(service._services.secret_repo, "app-secret")
    return service._services.sso_repo.upsert_by_kind(
        "feishu",
        enabled=True,
        display_name="Feishu",
        issuer="",
        client_id="cli_xxx",
        client_secret_enc=secret,
        scopes="",
        dashboard_origin=None,
        extra={"region": region},
    )


def test_feishu_authorize_url_omits_scope_and_uses_region_hosts(service: SsoService) -> None:
    adapter = FeishuAdapter(service)
    row = _feishu_row(service, region="lark")
    url = adapter.authorize_url(
        row=row,
        state="st",
        nonce="ignored",
        code_challenge="challenge",
        redirect_uri="https://octop.example/api/auth/oauth/callback",
    )
    assert "accounts.larksuite.com" in url
    query = httpx.QueryParams(url.split("?", 1)[1])
    assert query["client_id"] == "cli_xxx"
    assert query["response_type"] == "code"
    assert query["code_challenge_method"] == "S256"
    assert "scope" not in query


def test_feishu_is_configured_without_issuer(service: SsoService) -> None:
    adapter = FeishuAdapter(service)
    row = _feishu_row(service)
    assert adapter.is_configured(row)
    with patch.object(service._user_manager, "count", return_value=1):
        status = service.providers_status()
    feishu = next(item for item in status["providers"] if item["kind"] == "feishu")
    assert feishu["enabled"] is True


def test_feishu_complete_login_reads_v2_token_without_data_wrapper(
    service: SsoService,
) -> None:
    """authen/v2/oauth/token returns access_token at the top level, not in data."""
    adapter = FeishuAdapter(service)
    row = _feishu_row(service)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "access_token": "user-token",
                    "expires_in": 7200,
                    "token_type": "Bearer",
                },
            )
        return httpx.Response(
            200,
            json={"code": 0, "msg": "ok", "data": {"union_id": "on_union", "name": "Ada"}},
        )

    login_state = type("State", (), {"code_verifier": "pkce"})()
    real_client = httpx.Client

    def factory(*args: object, **kwargs: object) -> httpx.Client:
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    with patch("octop.infra.auth.sso.service.httpx.Client", side_effect=factory):
        subject, claims = adapter.complete_login(
            "auth-code",
            row=row,
            login_state=login_state,  # type: ignore[arg-type]
            redirect_uri="https://octop.example/api/auth/oauth/callback",
        )

    assert subject == "on_union"
    assert claims["name"] == "Ada"


def test_feishu_complete_login_unwraps_envelope_and_falls_back_to_open_id(
    service: SsoService,
) -> None:
    adapter = FeishuAdapter(service)
    row = _feishu_row(service)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/oauth/token"):
            body = json.loads(request.content)
            assert body["grant_type"] == "authorization_code"
            assert body["code_verifier"] == "pkce"
            assert request.headers["content-type"].startswith("application/json")
            return httpx.Response(
                200,
                json={"code": 0, "msg": "ok", "data": {"access_token": "user-token"}},
            )
        assert request.url.path.endswith("/user_info")
        assert request.headers["authorization"] == "Bearer user-token"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "ok",
                "data": {
                    "open_id": "ou_open",
                    "name": "Ada",
                    "enterprise_email": "ada@example.com",
                },
            },
        )

    login_state = type(
        "State",
        (),
        {"code_verifier": "pkce", "nonce": "n", "provider_id": row.id},
    )()
    real_client = httpx.Client

    def factory(*args: object, **kwargs: object) -> httpx.Client:
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    with patch("octop.infra.auth.sso.service.httpx.Client", side_effect=factory):
        subject, claims = adapter.complete_login(
            "auth-code",
            row=row,
            login_state=login_state,  # type: ignore[arg-type]
            redirect_uri="https://octop.example/api/auth/oauth/callback",
        )

    assert subject == "ou_open"
    assert claims["name"] == "Ada"
    assert claims["email"] == "ada@example.com"
    assert requests[0].method == "POST"


def test_feishu_token_envelope_error_is_value_error(service: SsoService) -> None:
    adapter = FeishuAdapter(service)
    row = _feishu_row(service)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 20027, "msg": "invalid scope", "data": {}})

    real_client = httpx.Client

    def factory(*args: object, **kwargs: object) -> httpx.Client:
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    login_state = type("State", (), {"code_verifier": "pkce"})()
    with (
        patch("octop.infra.auth.sso.service.httpx.Client", side_effect=factory),
        pytest.raises(ValueError, match="invalid scope"),
    ):
        adapter.complete_login(
            "auth-code",
            row=row,
            login_state=login_state,  # type: ignore[arg-type]
            redirect_uri="https://octop.example/api/auth/oauth/callback",
        )


def test_feishu_missing_subject_is_invalid_token(service: SsoService) -> None:
    adapter = FeishuAdapter(service)
    row = _feishu_row(service)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json={"code": 0, "msg": "ok", "data": {"access_token": "t"}})
        return httpx.Response(200, json={"code": 0, "msg": "ok", "data": {"name": "Ada"}})

    real_client = httpx.Client

    def factory(*args: object, **kwargs: object) -> httpx.Client:
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    login_state = type("State", (), {"code_verifier": "pkce"})()
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
