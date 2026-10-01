"""OpenID Connect dashboard login adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import httpx
import jwt

from octop.infra.auth.sso.public_base import oidc_callback_path
from octop.infra.db.repos.sso import SsoLoginStateRow, SsoProviderRow

if TYPE_CHECKING:
    from octop.infra.auth.sso.service import SsoService


class OidcAdapter:
    kind = "oidc"
    callback_path = oidc_callback_path()
    default_scopes = "openid profile email"

    def __init__(self, service: SsoService) -> None:
        self._service = service

    def is_configured(self, row: SsoProviderRow) -> bool:
        return bool(row.issuer.strip() and row.client_id.strip())

    def authorize_url(
        self,
        *,
        row: SsoProviderRow,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str:
        with self._service._http_client() as client:
            discovery = self._service._discovery.get(row.issuer, httpx_client=client)
        authorization_endpoint = self._service._endpoint(discovery, "authorization_endpoint")
        query = urlencode(
            {
                "response_type": "code",
                "client_id": row.client_id,
                "redirect_uri": redirect_uri,
                "scope": row.scopes,
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{authorization_endpoint}?{query}"

    def complete_login(
        self,
        code: str,
        *,
        row: SsoProviderRow,
        login_state: SsoLoginStateRow,
        redirect_uri: str,
    ) -> tuple[str, dict[str, Any]]:
        claims = self._service._exchange_claims(
            row,
            code,
            login_state.code_verifier,
            login_state.nonce,
            redirect_uri=redirect_uri,
        )
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise jwt.InvalidTokenError("token response has no subject")
        return subject, claims

    def test_connection(self, row: SsoProviderRow) -> dict[str, bool | str]:
        self._service._discovery.invalidate(row.issuer)
        try:
            with self._service._http_client() as client:
                discovery = self._service._discovery.get(row.issuer, httpx_client=client)
                jwks_uri = self._service._endpoint(discovery, "jwks_uri")
                response = client.get(jwks_uri)
                response.raise_for_status()
                jwks = response.json()
                if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
                    raise ValueError("JWKS response has no keys")
        except (httpx.HTTPError, ValueError) as exc:
            return {"ok": False, "detail": str(exc)}
        return {"ok": True, "detail": "OIDC discovery and JWKS are reachable"}
