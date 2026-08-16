"""OpenID Connect SSO service orchestration."""

from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from octop.infra.auth.sso.crypto import decrypt_secret, encrypt_secret
from octop.infra.auth.sso.discovery import DiscoveryCache
from octop.infra.auth.sso.id_token import verify_id_token
from octop.infra.auth.sso.pkce import new_pkce_pair
from octop.infra.auth.sso.public_base import build_redirect_uri
from octop.infra.auth.sso.redirect_after import sanitize_redirect_after
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.sso import SsoProviderRow
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User
from octop.infra.users.manager import UserManager

_LOGIN_STATE_TTL_SECONDS = 600
_LOGIN_CODE_TTL_SECONDS = 60
_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@dataclass(frozen=True)
class RedirectResult:
    """A browser redirect produced by an OIDC callback."""

    url: str


class SsoService:
    """Coordinates OIDC configuration and browser login flows."""

    def __init__(self, services: SharedServices, user_manager: UserManager) -> None:
        self._services = services
        self._user_manager = user_manager
        self._discovery = DiscoveryCache()

    def status(self) -> dict[str, bool | str]:
        provider = self._services.sso_repo.get_provider()
        enabled = bool(
            provider
            and provider.enabled
            and provider.issuer.strip()
            and self._user_manager.count() > 0
        )
        return {
            "enabled": enabled,
            "display_name": provider.display_name if provider is not None else "",
        }

    def get_config_for_admin(self, *, public_base: str) -> dict[str, Any]:
        provider = self._services.sso_repo.get_provider()
        if provider is None:
            return {
                "enabled": False,
                "display_name": "",
                "issuer": "",
                "client_id": "",
                "scopes": "openid profile email",
                "dashboard_origin": None,
                "has_client_secret": False,
                "redirect_uri": build_redirect_uri(public_base),
            }
        return {
            "enabled": bool(provider.enabled),
            "display_name": provider.display_name,
            "issuer": provider.issuer,
            "client_id": provider.client_id,
            "scopes": provider.scopes,
            "dashboard_origin": provider.dashboard_origin,
            "has_client_secret": provider.client_secret_enc is not None,
            "redirect_uri": build_redirect_uri(public_base),
        }

    def put_config(
        self,
        body: Mapping[str, object],
        *,
        secret_repo: SecretRepo | None = None,
        public_base: str | None = None,
    ) -> dict[str, Any]:
        current = self._services.sso_repo.get_provider()
        secret = body.get("client_secret")
        encrypted_secret: bytes | None = None
        if isinstance(secret, str) and secret:
            encrypted_secret = encrypt_secret(secret_repo or self._services.secret_repo, secret)

        provider = self._services.sso_repo.upsert_provider(
            enabled=bool(body.get("enabled", current.enabled if current else False)),
            display_name=self._string(body, "display_name", current, "Octop SSO"),
            issuer=self._string(body, "issuer", current, ""),
            client_id=self._string(body, "client_id", current, ""),
            client_secret_enc=encrypted_secret,
            scopes=self._string(body, "scopes", current, "openid profile email"),
            dashboard_origin=self._nullable_string(body, "dashboard_origin", current),
        )
        self._discovery.invalidate(provider.issuer)
        if public_base is not None:
            return self.get_config_for_admin(public_base=public_base)
        return self._provider_config(provider)

    def test_connection(self) -> dict[str, bool | str]:
        provider = self._configured_provider()
        self._discovery.invalidate(provider.issuer)
        try:
            with self._http_client() as client:
                discovery = self._discovery.get(provider.issuer, httpx_client=client)
                jwks_uri = self._endpoint(discovery, "jwks_uri")
                response = client.get(jwks_uri)
                response.raise_for_status()
                jwks = response.json()
                if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
                    raise ValueError("JWKS response has no keys")
        except (httpx.HTTPError, ValueError) as exc:
            return {"ok": False, "detail": str(exc)}
        return {"ok": True, "detail": "OIDC discovery and JWKS are reachable"}

    def start_login(self, *, redirect_after: str | None, public_base: str) -> dict[str, str]:
        self._services.sso_repo.delete_expired()
        provider = self._enabled_provider()
        nonce = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(32)
        verifier, challenge = new_pkce_pair()
        redirect_uri = build_redirect_uri(public_base)
        with self._http_client() as client:
            discovery = self._discovery.get(provider.issuer, httpx_client=client)
        authorization_endpoint = self._endpoint(discovery, "authorization_endpoint")
        self._services.sso_repo.create_login_state(
            state=state,
            provider_id=provider.id,
            nonce=nonce,
            code_verifier=verifier,
            redirect_after=sanitize_redirect_after(redirect_after),
            expires_at=int(time.time()) + _LOGIN_STATE_TTL_SECONDS,
        )
        query = urlencode(
            {
                "response_type": "code",
                "client_id": provider.client_id,
                "redirect_uri": redirect_uri,
                "scope": provider.scopes,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return {
            "authorization_url": f"{authorization_endpoint}?{query}",
            "state": state,
        }

    async def handle_callback(
        self,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
        public_base: str,
    ) -> RedirectResult:
        self._services.sso_repo.delete_expired()
        frontend = self._frontend_base(public_base)
        if error is not None:
            return self._error_redirect(
                frontend, "denied" if error == "access_denied" else "generic"
            )
        if not state:
            return self._error_redirect(frontend, "state")

        login_state = self._services.sso_repo.take_login_state(state)
        if login_state is None:
            return self._error_redirect(frontend, "state")
        provider = self._services.sso_repo.get_provider()
        if provider is None or provider.id != login_state.provider_id or not provider.enabled:
            return self._error_redirect(frontend, "disabled")
        if not provider.issuer.strip() or not provider.client_id.strip() or not code:
            return self._error_redirect(frontend, "misconfigured")

        # Prefer configured dashboard origin once provider is known.
        frontend = self._frontend_base(public_base, provider=provider)

        try:
            claims = await asyncio.get_running_loop().run_in_executor(
                None,
                partial(
                    self._exchange_claims,
                    provider,
                    code,
                    login_state.code_verifier,
                    login_state.nonce,
                    public_base,
                ),
            )
        except jwt.InvalidTokenError:
            return self._error_redirect(frontend, "invalid_token")
        except (httpx.HTTPError, ValueError):
            return self._error_redirect(frontend, "exchange")

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            return self._error_redirect(frontend, "invalid_token")
        try:
            user = await self._user_manager.resolve_or_create_sso_user(
                provider_id=provider.id, subject=subject, claims=claims
            )
        except OctopError as exc:
            if exc.code is ErrorCode.USER_DISABLED:
                return self._error_redirect(frontend, "disabled")
            return self._error_redirect(frontend, "generic")
        except Exception:
            return self._error_redirect(frontend, "generic")

        login_code = secrets.token_urlsafe(32)
        self._services.sso_repo.attach_login_code(
            state,
            login_code=login_code,
            user_id=user.id,
            expires_at=int(time.time()) + _LOGIN_CODE_TTL_SECONDS,
        )
        # Put credentials in the URL fragment so they are not sent to the server
        # or written to typical access logs for the complete page request.
        return RedirectResult(
            f"{frontend}/login/oidc/complete#"
            f"{urlencode({'code': login_code, 'redirect': login_state.redirect_after})}"
        )

    async def exchange_login_code(self, code: str) -> User:
        consumed = self._services.sso_repo.consume_login_code(code)
        if consumed is None:
            raise ValueError("invalid or expired SSO login code")
        user = self._user_manager.get_by_id(consumed["user_id"])
        if user is None:
            raise ValueError("SSO user is unavailable")
        self._services.audit_repo.write(
            actor=user.username, action="auth.oidc_login", target=user.username
        )
        return user

    def _enabled_provider(self) -> SsoProviderRow:
        provider = self._services.sso_repo.get_provider()
        if provider is None or not provider.enabled or self._user_manager.count() == 0:
            raise ValueError("SSO is disabled")
        if not provider.issuer.strip() or not provider.client_id.strip():
            raise ValueError("SSO is misconfigured")
        return provider

    def _configured_provider(self) -> SsoProviderRow:
        provider = self._services.sso_repo.get_provider()
        if provider is None or not provider.issuer.strip() or not provider.client_id.strip():
            raise ValueError("SSO is misconfigured")
        return provider

    def _frontend_base(self, public_base: str, *, provider: SsoProviderRow | None = None) -> str:
        row = provider if provider is not None else self._services.sso_repo.get_provider()
        origin = row.dashboard_origin if row is not None else None
        return (origin or public_base).rstrip("/")

    def login_error_frontend(self, public_base: str) -> str:
        """Resolve where OIDC error redirects should land (dashboard_origin when set)."""
        return self._frontend_base(public_base)

    @staticmethod
    def _http_client() -> httpx.Client:
        return httpx.Client(timeout=_HTTP_TIMEOUT)

    @staticmethod
    def _endpoint(discovery: Mapping[str, object], name: str) -> str:
        endpoint = discovery.get(name)
        if not isinstance(endpoint, str) or not endpoint:
            raise ValueError(f"OIDC discovery has no {name}")
        return endpoint

    def _token_request_data(
        self, provider: SsoProviderRow, code: str, verifier: str, public_base: str
    ) -> dict[str, str]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": build_redirect_uri(public_base),
            "client_id": provider.client_id,
            "code_verifier": verifier,
        }
        if provider.client_secret_enc is not None:
            data["client_secret"] = decrypt_secret(
                self._services.secret_repo, provider.client_secret_enc
            )
        return data

    def _exchange_claims(
        self,
        provider: SsoProviderRow,
        code: str,
        code_verifier: str,
        nonce: str,
        public_base: str,
    ) -> dict[str, Any]:
        with self._http_client() as client:
            discovery = self._discovery.get(provider.issuer, httpx_client=client)
            token_endpoint = self._endpoint(discovery, "token_endpoint")
            jwks_uri = self._endpoint(discovery, "jwks_uri")
            token_response = client.post(
                token_endpoint,
                data=self._token_request_data(provider, code, code_verifier, public_base),
            )
            token_response.raise_for_status()
            token = token_response.json()
            id_token = token.get("id_token") if isinstance(token, dict) else None
            if not isinstance(id_token, str):
                raise jwt.InvalidTokenError("token response has no ID token")
            return verify_id_token(
                id_token,
                jwks_uri=jwks_uri,
                issuer=provider.issuer.rstrip("/"),
                client_id=provider.client_id,
                nonce=nonce,
                httpx=client,
            )

    @staticmethod
    def _string(
        body: Mapping[str, object],
        name: str,
        current: SsoProviderRow | None,
        default: str,
    ) -> str:
        value = body.get(name)
        if isinstance(value, str):
            return value.strip()
        return str(getattr(current, name)) if current is not None else default

    @staticmethod
    def _nullable_string(
        body: Mapping[str, object], name: str, current: SsoProviderRow | None
    ) -> str | None:
        if name in body:
            value = body[name]
            return value.strip() if isinstance(value, str) and value.strip() else None
        return getattr(current, name) if current is not None else None

    @staticmethod
    def _provider_config(provider: SsoProviderRow) -> dict[str, Any]:
        return {
            "enabled": bool(provider.enabled),
            "display_name": provider.display_name,
            "issuer": provider.issuer,
            "client_id": provider.client_id,
            "scopes": provider.scopes,
            "dashboard_origin": provider.dashboard_origin,
            "has_client_secret": provider.client_secret_enc is not None,
        }

    @staticmethod
    def _error_redirect(frontend_base: str, oidc_error: str) -> RedirectResult:
        return RedirectResult(
            f"{frontend_base.rstrip('/')}/login?{urlencode({'oidc_error': oidc_error})}"
        )
