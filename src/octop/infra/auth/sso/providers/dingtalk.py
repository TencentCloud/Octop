"""DingTalk enterprise-app web OAuth dashboard login adapter."""

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

_AUTHORIZE = "https://login.dingtalk.com/oauth2/auth"
_API = "https://api.dingtalk.com"
_OAPI = "https://oapi.dingtalk.com"


class DingTalkAdapter:
    kind = "dingtalk"
    callback_path = oauth_callback_path()
    default_scopes = "openid"

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
        del nonce, code_challenge  # DingTalk web login does not use OIDC nonce / PKCE.
        scopes = row.scopes.strip() or self.default_scopes
        params = {
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "client_id": row.client_id,
            "scope": scopes,
            "state": state,
            "prompt": "consent",
        }
        return f"{_AUTHORIZE}?{urlencode(params)}"

    def complete_login(
        self,
        code: str,
        *,
        row: SsoProviderRow,
        login_state: SsoLoginStateRow,
        redirect_uri: str,
    ) -> tuple[str, dict[str, Any]]:
        del redirect_uri, login_state  # Token exchange does not use redirect_uri / PKCE.
        if row.client_secret_enc is None:
            raise ValueError("DingTalk app secret is not configured")
        secret = decrypt_secret(self._service._services.secret_repo, row.client_secret_enc)
        with self._service._http_client() as client:
            token_response = client.post(
                f"{_API}/v1.0/oauth2/userAccessToken",
                json={
                    "clientId": row.client_id,
                    "clientSecret": secret,
                    "code": code,
                    "grantType": "authorization_code",
                },
            )
            try:
                token_response.raise_for_status()
                token_data = token_response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ValueError(str(exc)) from exc
            if not isinstance(token_data, dict):
                raise ValueError("DingTalk token response is not an object")
            access_token = token_data.get("accessToken")
            if not isinstance(access_token, str) or not access_token:
                raise jwt.InvalidTokenError("DingTalk token response has no accessToken")
            user_response = client.get(
                f"{_API}/v1.0/contact/users/me",
                headers={"x-acs-dingtalk-access-token": access_token},
            )
            try:
                user_response.raise_for_status()
                identity = user_response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ValueError(str(exc)) from exc
        if not isinstance(identity, dict):
            raise ValueError("DingTalk user info is not an object")
        subject = identity.get("unionId") or identity.get("openId")
        if not isinstance(subject, str) or not subject:
            raise jwt.InvalidTokenError("DingTalk user info has no unionId or openId")
        return subject, self.to_claims(identity)

    def test_connection(self, row: SsoProviderRow) -> dict[str, bool | str]:
        if row.client_secret_enc is None:
            return {"ok": False, "detail": "DingTalk app secret is not configured"}
        secret = decrypt_secret(self._service._services.secret_repo, row.client_secret_enc)
        try:
            with self._service._http_client() as client:
                response = client.get(
                    f"{_OAPI}/gettoken",
                    params={"appkey": row.client_id, "appsecret": secret},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {"ok": False, "detail": str(exc)}
        if not isinstance(payload, dict):
            return {"ok": False, "detail": "DingTalk token response is not an object"}
        if payload.get("errcode") not in (0, "0", None):
            errmsg = payload.get("errmsg")
            detail = (
                errmsg if isinstance(errmsg, str) and errmsg else "DingTalk credential check failed"
            )
            return {"ok": False, "detail": detail}
        if not payload.get("access_token"):
            return {"ok": False, "detail": "DingTalk credential check returned no access_token"}
        return {"ok": True, "detail": "DingTalk app credentials are valid"}

    @staticmethod
    def to_claims(identity: dict[str, Any]) -> dict[str, Any]:
        claims: dict[str, Any] = {}
        nick = identity.get("nick")
        email = identity.get("email")
        if isinstance(nick, str) and nick.strip():
            claims["name"] = nick.strip()
        if isinstance(email, str) and email.strip():
            claims["email"] = email.strip()
        return claims
