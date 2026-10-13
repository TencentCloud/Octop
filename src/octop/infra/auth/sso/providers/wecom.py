"""WeCom (企业微信) CorpApp web login adapter for dashboard SSO."""

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

# Browser / QR web login (path 98152), not in-WeCom oauth2 authorize.
_AUTHORIZE = "https://login.work.weixin.qq.com/wwlogin/sso/login"
_API = "https://qyapi.weixin.qq.com"


def wecom_agent_id(row: SsoProviderRow) -> str:
    raw = row.extra.get("agent_id")
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return ""


class WeComAdapter:
    kind = "wecom"
    callback_path = oauth_callback_path()
    default_scopes = ""

    def __init__(self, service: SsoService) -> None:
        self._service = service

    def is_configured(self, row: SsoProviderRow) -> bool:
        return bool(
            row.client_id.strip() and row.client_secret_enc is not None and wecom_agent_id(row)
        )

    def authorize_url(
        self,
        *,
        row: SsoProviderRow,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str:
        del nonce, code_challenge
        agent_id = wecom_agent_id(row)
        if not agent_id:
            raise ValueError("WeCom Agent ID is not configured")
        params = {
            "login_type": "CorpApp",
            "appid": row.client_id,
            "agentid": agent_id,
            "redirect_uri": redirect_uri,
            "state": state,
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
        del redirect_uri, login_state
        if row.client_secret_enc is None:
            raise ValueError("WeCom app secret is not configured")
        secret = decrypt_secret(self._service._services.secret_repo, row.client_secret_enc)
        with self._service._http_client() as client:
            access_token = self._access_token(client, corpid=row.client_id, secret=secret)
            user_response = client.get(
                f"{_API}/cgi-bin/auth/getuserinfo",
                params={"access_token": access_token, "code": code},
            )
            try:
                user_response.raise_for_status()
                identity = user_response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ValueError(str(exc)) from exc
            if not isinstance(identity, dict):
                raise ValueError("WeCom user info is not an object")
            errcode = identity.get("errcode", 0)
            if errcode not in (0, "0", None):
                errmsg = identity.get("errmsg")
                detail = errmsg if isinstance(errmsg, str) and errmsg else f"WeCom error {errcode}"
                raise ValueError(detail)
            userid = identity.get("userid")
            if not isinstance(userid, str) or not userid:
                raise jwt.InvalidTokenError("WeCom user info has no userid")
            claims = self._member_claims(client, access_token=access_token, userid=userid)
            user_ticket = identity.get("user_ticket")
            if isinstance(user_ticket, str) and user_ticket:
                claims.update(
                    self._sensitive_claims(
                        client, access_token=access_token, user_ticket=user_ticket
                    )
                )
        return userid, claims

    def test_connection(self, row: SsoProviderRow) -> dict[str, bool | str]:
        if row.client_secret_enc is None:
            return {"ok": False, "detail": "WeCom app secret is not configured"}
        if not wecom_agent_id(row):
            return {"ok": False, "detail": "WeCom Agent ID is not configured"}
        secret = decrypt_secret(self._service._services.secret_repo, row.client_secret_enc)
        try:
            with self._service._http_client() as client:
                self._access_token(client, corpid=row.client_id, secret=secret)
        except (httpx.HTTPError, ValueError) as exc:
            return {"ok": False, "detail": str(exc)}
        return {"ok": True, "detail": "WeCom app credentials are valid"}

    @staticmethod
    def _access_token(client: httpx.Client, *, corpid: str, secret: str) -> str:
        response = client.get(
            f"{_API}/cgi-bin/gettoken",
            params={"corpid": corpid, "corpsecret": secret},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("WeCom token response is not an object")
        errcode = payload.get("errcode", 0)
        if errcode not in (0, "0", None):
            errmsg = payload.get("errmsg")
            detail = errmsg if isinstance(errmsg, str) and errmsg else f"WeCom error {errcode}"
            raise ValueError(detail)
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("WeCom token response has no access_token")
        return token

    @staticmethod
    def _member_claims(client: httpx.Client, *, access_token: str, userid: str) -> dict[str, Any]:
        response = client.get(
            f"{_API}/cgi-bin/user/get",
            params={"access_token": access_token, "userid": userid},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("errcode", 0) not in (0, "0", None):
            return {}
        claims: dict[str, Any] = {}
        name = payload.get("name")
        email = payload.get("biz_mail") or payload.get("email")
        if isinstance(name, str) and name.strip():
            claims["name"] = name.strip()
        if isinstance(email, str) and email.strip():
            claims["email"] = email.strip()
        return claims

    @staticmethod
    def _sensitive_claims(
        client: httpx.Client, *, access_token: str, user_ticket: str
    ) -> dict[str, Any]:
        response = client.post(
            f"{_API}/cgi-bin/auth/getuserdetail",
            params={"access_token": access_token},
            json={"user_ticket": user_ticket},
        )
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return {}
        if not isinstance(payload, dict) or payload.get("errcode", 0) not in (0, "0", None):
            return {}
        claims: dict[str, Any] = {}
        email = payload.get("biz_mail") or payload.get("email")
        if isinstance(email, str) and email.strip():
            claims["email"] = email.strip()
        return claims
