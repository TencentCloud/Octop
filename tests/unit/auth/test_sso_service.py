"""Tests for OIDC SSO service orchestration."""

from __future__ import annotations

import time
from unittest.mock import patch

import httpx
import jwt
import pytest

from octop.config import OctopConfig
from octop.infra.auth.sso.crypto import decrypt_secret
from octop.infra.auth.sso.service import SsoService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.users.identity import Role, User
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


def configure_provider(
    service: SsoService,
    *,
    enabled: bool = True,
    issuer: str = "https://issuer.example/",
    client_id: str = "client-id",
    display_name: str = "Example ID",
    dashboard_origin: str | None = None,
):
    return service._services.sso_repo.upsert_provider(
        enabled=enabled,
        display_name=display_name,
        issuer=issuer,
        client_id=client_id,
        client_secret_enc=None,
        scopes="openid profile email",
        dashboard_origin=dashboard_origin,
    )


def add_login_state(service: SsoService, provider_id: int, state: str = "valid-state") -> None:
    service._services.sso_repo.create_login_state(
        state=state,
        provider_id=provider_id,
        nonce="expected-nonce",
        code_verifier="pkce-verifier",
        redirect_after="/chat",
        expires_at=int(time.time()) + 600,
    )


def discovery_client(handler):
    real_httpx_client = httpx.Client

    def factory(*args: object, **kwargs: object) -> httpx.Client:
        kwargs.pop("transport", None)
        return real_httpx_client(
            *args,
            transport=httpx.MockTransport(handler),
            **kwargs,  # type: ignore[arg-type]
        )

    return patch("octop.infra.auth.sso.service.httpx.Client", side_effect=factory)


@pytest.mark.parametrize(
    ("provider", "user_count"),
    [
        (None, 0),
        ({"enabled": False}, 1),
        ({"issuer": "   "}, 1),
        ({}, 0),
    ],
)
def test_status_is_disabled_without_usable_provider_or_users(
    service: SsoService, provider: dict[str, object] | None, user_count: int
) -> None:
    if provider is not None:
        configure_provider(
            service,
            enabled=bool(provider.get("enabled", True)),
            issuer=str(provider.get("issuer", "https://issuer.example/")),
        )
    with patch.object(service._user_manager, "count", return_value=user_count):
        assert service.status()["enabled"] is False


def test_status_returns_enabled_provider_display_name(service: SsoService) -> None:
    configure_provider(service, display_name="Company Login")
    with patch.object(service._user_manager, "count", return_value=1):
        assert service.status() == {"enabled": True, "display_name": "Company Login"}


def test_put_config_encrypts_with_supplied_secret_repo_and_redacts_for_admin(
    service: SsoService,
) -> None:
    with patch(
        "octop.infra.auth.sso.service.encrypt_secret", return_value=b"ciphertext"
    ) as encrypt:
        result = service.put_config(
            {
                "enabled": True,
                "display_name": "Company Login",
                "issuer": "https://issuer.example/",
                "client_id": "client-id",
                "client_secret": "top-secret",
            },
            secret_repo=service._services.secret_repo,
        )

    assert encrypt.call_args.args == (service._services.secret_repo, "top-secret")
    assert result["has_client_secret"] is True
    assert service.get_config_for_admin(public_base="https://octop.example") == {
        "enabled": True,
        "display_name": "Company Login",
        "issuer": "https://issuer.example/",
        "client_id": "client-id",
        "scopes": "openid profile email",
        "dashboard_origin": None,
        "has_client_secret": True,
        "redirect_uri": "https://octop.example/api/auth/oidc/callback",
    }
    assert "client_secret" not in result
    assert service._services.sso_repo.get_provider().client_secret_enc == b"ciphertext"


def test_put_config_encrypts_secret_and_empty_secret_keeps_previous_value(
    service: SsoService,
) -> None:
    service.put_config(
        {
            "issuer": "https://issuer.example/",
            "client_id": "client-id",
            "client_secret": "top-secret",
        }
    )
    first = service._services.sso_repo.get_provider()
    assert first is not None
    assert decrypt_secret(service._services.secret_repo, first.client_secret_enc) == "top-secret"

    service.put_config({"client_secret": ""})
    second = service._services.sso_repo.get_provider()
    assert second is not None
    assert second.client_secret_enc == first.client_secret_enc


def test_start_login_when_disabled_raises(service: SsoService) -> None:
    with pytest.raises(ValueError, match="disabled"):
        service.start_login(redirect_after="/chat", public_base="https://octop.example")


def test_start_login_persists_pkce_state_and_uses_s256(service: SsoService) -> None:
    service._services.user_repo.create(username="admin", role="admin")
    provider = configure_provider(service)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/.well-known/openid-configuration"
        return httpx.Response(
            200,
            json={
                "issuer": "https://issuer.example",
                "authorization_endpoint": "https://issuer.example/authorize",
            },
        )

    with discovery_client(handler):
        started = service.start_login(
            redirect_after="https://attacker.example", public_base="https://octop.example"
        )

    query = httpx.QueryParams(started["authorization_url"].split("?", 1)[1])
    assert started["state"] == query["state"]
    persisted = service._services.sso_repo.take_login_state(query["state"])
    assert persisted is not None
    assert persisted.provider_id == provider.id
    assert persisted.nonce == query["nonce"]
    assert persisted.code_verifier
    assert query["code_challenge"]
    assert query["code_challenge_method"] == "S256"
    assert query["redirect_uri"] == "https://octop.example/api/auth/oidc/callback"
    assert persisted.redirect_after == "/chat"
    assert service._services.sso_repo.take_login_state(query["state"]) is None


@pytest.mark.asyncio
async def test_callback_error_redirect_prefers_dashboard_origin(service: SsoService) -> None:
    configure_provider(service, dashboard_origin="https://dashboard.example")
    denied = await service.handle_callback(
        code=None, state=None, error="access_denied", public_base="https://api.example"
    )
    assert denied.url == "https://dashboard.example/login?oidc_error=denied"


@pytest.mark.asyncio
async def test_callback_maps_denied_bad_state_and_invalid_token(service: SsoService) -> None:
    denied = await service.handle_callback(
        code=None, state=None, error="access_denied", public_base="https://octop.example"
    )
    bad_state = await service.handle_callback(
        code="code", state="unknown", error=None, public_base="https://octop.example"
    )
    assert denied.url == "https://octop.example/login?oidc_error=denied"
    assert bad_state.url == "https://octop.example/login?oidc_error=state"

    provider = configure_provider(service)
    add_login_state(service, provider.id)
    with patch.object(service, "_exchange_claims", side_effect=jwt.InvalidTokenError):
        invalid = await service.handle_callback(
            code="code", state="valid-state", error=None, public_base="https://octop.example"
        )
    assert invalid.url == "https://octop.example/login?oidc_error=invalid_token"


@pytest.mark.asyncio
async def test_callback_exchanges_code_and_attaches_login_code(service: SsoService) -> None:
    service._services.user_repo.create(username="admin", role="admin")
    configure_provider(service)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": "https://issuer.example",
                    "authorization_endpoint": "https://issuer.example/authorize",
                    "token_endpoint": "https://issuer.example/token",
                    "jwks_uri": "https://issuer.example/jwks",
                },
            )
        assert request.url.path == "/token"
        return httpx.Response(200, json={"id_token": "signed-id-token"})

    with (
        discovery_client(handler),
        patch(
            "octop.infra.auth.sso.service.verify_id_token",
            return_value={
                "sub": "subject-123",
                "email": "member@example.com",
                "preferred_username": "member",
            },
        ),
    ):
        started = service.start_login(
            redirect_after="/settings", public_base="https://octop.example"
        )
        state = httpx.QueryParams(started["authorization_url"].split("?", 1)[1])["state"]
        result = await service.handle_callback(
            code="authorization-code",
            state=state,
            error=None,
            public_base="https://octop.example",
        )

    assert result.url.startswith("https://octop.example/login/oidc/complete#code=")
    assert "redirect=%2Fsettings" in result.url
    assert requests[-1].url == httpx.URL("https://issuer.example/token")
    assert requests[-1].method == "POST"
    user_id = service._services.sso_repo.consume_login_code(
        httpx.QueryParams(result.url.split("#", 1)[1])["code"]
    )
    assert user_id is not None
    assert service._services.user_repo.get(user_id["user_id"]).username == "member"


@pytest.mark.asyncio
async def test_exchange_login_code_is_one_shot_and_writes_audit(service: SsoService) -> None:
    user = User(id=42, username="member", role=Role.USER, display_name=None)
    provider = configure_provider(service)
    add_login_state(service, provider.id)
    service._services.sso_repo.attach_login_code(
        "valid-state", login_code="one-shot", user_id=user.id, expires_at=int(time.time()) + 60
    )
    with patch.object(service._user_manager, "get_by_id", return_value=user):
        assert await service.exchange_login_code("one-shot") == user
        with pytest.raises(ValueError, match="invalid or expired"):
            await service.exchange_login_code("one-shot")
        with pytest.raises(ValueError, match="invalid or expired"):
            await service.exchange_login_code("unknown")

    audit = service._services.audit_repo.query(action="auth.oidc_login")
    assert [(row.actor, row.target) for row in audit] == [("member", "member")]


@pytest.mark.asyncio
async def test_exchange_login_code_rejects_unavailable_user(service: SsoService) -> None:
    provider = configure_provider(service)
    add_login_state(service, provider.id)
    service._services.sso_repo.attach_login_code(
        "valid-state", login_code="unavailable", user_id=42, expires_at=int(time.time()) + 60
    )
    with (
        patch.object(service._user_manager, "get_by_id", return_value=None),
        pytest.raises(ValueError, match="unavailable"),
    ):
        await service.exchange_login_code("unavailable")
