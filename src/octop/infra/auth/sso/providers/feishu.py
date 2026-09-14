"""Feishu / Lark web OAuth dashboard login adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import httpx
import jwt

from octop.infra.auth.sso.crypto import decrypt_secret
from octop.infra.auth.sso.public_base import oauth_callback_path
from octop.infra.db.repos.sso import SsoLoginStateRow, SsoProviderRow

if TYPE_CHECKING:
    from octop.infra.auth.sso.service import SsoService

_FEISHU_ACCOUNTS = {
    "feishu": "https://accounts.feishu.cn",
    "lark": "https://accounts.larksuite.com",
}
_FEISHU_OPEN = {
    "feishu": "https://open.feishu.cn",
    "lark": "https://open.larksuite.com",
}


def feishu_region(row: SsoProviderRow) -> str:
    raw = row.extra.get("region")
    if raw == "lark":
        return "lark"
    return "feishu"


def _unwrap(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Feishu response is not an object")
    code = payload.get("code")
    if code not in (0, "0"):
        msg = payload.get("msg")
        detail = msg if isinstance(msg, str) and msg else f"Feishu error {code}"
        raise ValueError(detail)
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    if data is None:
        # authen/v2/oauth/token puts access_token at the top level.
        return payload
    raise ValueError("Feishu response has no data object")


class FeishuAdapter:
    kind = "feishu"
    callback_path = oauth_callback_path()
    default_scopes = ""

    def __init__(self, service: SsoService) -> None:
        self._service = service

    def is_configured(self, row: SsoProviderRow) -> bool:
        return bool(row.client_id.strip() and row.client_secret_enc is not None)

    def authorize_url(
        self,
        *,
        row: SsoProviderRow,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str:
        del nonce  # Feishu authorize does not use OIDC nonce.
        region = feishu_region(row)
        params: dict[str, str] = {
            "client_id": row.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        scopes = row.scopes.strip()
        if scopes:
            params["scope"] = scopes
        return f"{_FEISHU_ACCOUNTS[region]}/open-apis/authen/v1/authorize?{urlencode(params)}"

    def complete_login(
        self,
        code: str,
        *,
        row: SsoProviderRow,
        login_state: SsoLoginStateRow,
        redirect_uri: str,
    ) -> tuple[str, dict[str, Any]]:
        if row.client_secret_enc is None:
            raise ValueError("Feishu app secret is not configured")
        secret = decrypt_secret(self._service._services.secret_repo, row.client_secret_enc)
        open_base = _FEISHU_OPEN[feishu_region(row)]
        with self._service._http_client() as client:
            token_response = client.post(
                f"{open_base}/open-apis/authen/v2/oauth/token",
                json={
                    "grant_type": "authorization_code",
                    "client_id": row.client_id,
                    "client_secret": secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": login_state.code_verifier,
                },
            )
            try:
                token_response.raise_for_status()
                token_data = _unwrap(token_response.json())
            except (httpx.HTTPError, ValueError) as exc:
                raise ValueError(str(exc)) from exc
            access_token = token_data.get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise jwt.InvalidTokenError("Feishu token response has no access_token")
            user_response = client.get(
                f"{open_base}/open-apis/authen/v1/user_info",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            try:
                user_response.raise_for_status()
                identity = _unwrap(user_response.json())
            except (httpx.HTTPError, ValueError) as exc:
                raise ValueError(str(exc)) from exc
        subject = identity.get("union_id") or identity.get("open_id")
        if not isinstance(subject, str) or not subject:
            raise jwt.InvalidTokenError("Feishu user info has no union_id or open_id")
        return subject, self.to_claims(identity)

    def test_connection(self, row: SsoProviderRow) -> dict[str, bool | str]:
        if row.client_secret_enc is None:
            return {"ok": False, "detail": "Feishu app secret is not configured"}
        secret = decrypt_secret(self._service._services.secret_repo, row.client_secret_enc)
        open_base = _FEISHU_OPEN[feishu_region(row)]
        try:
            with self._service._http_client() as client:
                response = client.post(
                    f"{open_base}/open-apis/auth/v3/app_access_token/internal",
                    json={"app_id": row.client_id, "app_secret": secret},
                )
                response.raise_for_status()
                _unwrap(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            return {"ok": False, "detail": str(exc)}
        return {"ok": True, "detail": "Feishu app credentials are valid"}

    @staticmethod
    def to_claims(identity: dict[str, Any]) -> dict[str, Any]:
        name = identity.get("name")
        email = identity.get("email") or identity.get("enterprise_email")
        claims: dict[str, Any] = {}
        if isinstance(name, str) and name.strip():
            claims["name"] = name.strip()
        if isinstance(email, str) and email.strip():
            claims["email"] = email.strip()
        return claims
