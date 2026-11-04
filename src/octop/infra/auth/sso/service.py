"""SSO service orchestration for OIDC and pluggable OAuth providers."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
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
from octop.infra.auth.sso.providers import build_adapters
from octop.infra.auth.sso.providers.base import SSO_KINDS, IdentityProvider
from octop.infra.auth.sso.public_base import build_redirect_uri, parse_strict_origin
from octop.infra.auth.sso.redirect_after import sanitize_redirect_after
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.sso import SsoProviderRow
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User
from octop.infra.users.manager import UserManager

_LOGIN_STATE_TTL_SECONDS = 600
_LOGIN_CODE_TTL_SECONDS = 60
# 浏览器一次性登录码有效期（秒）；路由响应用同一常量，避免与签发 TTL 漂移
LOGIN_CODE_TTL_SECONDS = _LOGIN_CODE_TTL_SECONDS
_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RedirectResult:
    """A browser redirect produced by an OIDC callback."""

    url: str


class SsoService:
    """Coordinates SSO configuration and browser login / bind flows."""

    def __init__(self, services: SharedServices, user_manager: UserManager) -> None:
        self._services = services
        self._user_manager = user_manager
        self._discovery = DiscoveryCache()
        self._adapters: dict[str, IdentityProvider] = build_adapters(self)

    def status(self) -> dict[str, bool | str]:
        provider = self._services.sso_repo.get_provider()
        adapter = self._adapters["oidc"]
        enabled = bool(
            provider
            and provider.enabled
            and adapter.is_configured(provider)
            and self._user_manager.count() > 0
        )
        return {
            "enabled": enabled,
            "display_name": provider.display_name if provider is not None else "",
        }

    def providers_status(self) -> dict[str, list[dict[str, bool | str]]]:
        rows = {row.kind: row for row in self._services.sso_repo.list()}
        users_exist = self._user_manager.count() > 0
        providers: list[dict[str, bool | str]] = []
        for kind in SSO_KINDS:
            adapter = self._adapters[kind]
            row = rows.get(kind)
            enabled = bool(
                row is not None and row.enabled and adapter.is_configured(row) and users_exist
            )
            providers.append(
                {
                    "kind": kind,
                    "display_name": row.display_name if row is not None else "",
                    "enabled": enabled,
                }
            )
        return {"providers": providers}

    def get_config_for_admin(self, *, public_base: str) -> dict[str, Any]:
        config = self.get_config_for_kind("oidc", public_base=public_base)
        config.pop("kind", None)
        config.pop("extra", None)
        return config

    def get_config_for_kind(self, kind: str, *, public_base: str) -> dict[str, Any]:
        adapter = self._adapter(kind)
        provider = self._services.sso_repo.get_by_kind(kind)
        redirect_uri = build_redirect_uri(public_base, adapter.callback_path)
        if provider is None:
            config: dict[str, Any] = {
                "kind": kind,
                "enabled": False,
                "display_name": "",
                "issuer": "",
                "client_id": "",
                "scopes": adapter.default_scopes,
                "dashboard_origin": None,
                "has_client_secret": False,
                "redirect_uri": redirect_uri,
                "extra": {},
            }
        else:
            config = {
                "kind": kind,
                "enabled": bool(provider.enabled),
                "display_name": provider.display_name,
                "issuer": provider.issuer,
                "client_id": provider.client_id,
                "scopes": provider.scopes,
                "dashboard_origin": provider.dashboard_origin,
                "has_client_secret": provider.client_secret_enc is not None,
                "redirect_uri": redirect_uri,
                "extra": dict(provider.extra),
            }
        if kind == "external":
            # external 的 callback 仅为占位路径，不对外展示 redirect_uri
            config.pop("redirect_uri", None)
        return config

    def put_config(
        self,
        body: Mapping[str, object],
        *,
        secret_repo: SecretRepo | None = None,
        public_base: str | None = None,
    ) -> dict[str, Any]:
        result = self.put_config_for_kind(
            "oidc", body, secret_repo=secret_repo, public_base=public_base
        )
        result.pop("kind", None)
        result.pop("extra", None)
        return result

    def put_config_for_kind(
        self,
        kind: str,
        body: Mapping[str, object],
        *,
        secret_repo: SecretRepo | None = None,
        public_base: str | None = None,
    ) -> dict[str, Any]:
        adapter = self._adapter(kind)
        current = self._services.sso_repo.get_by_kind(kind)
        secret = body.get("client_secret")
        # external 的共享密钥用于 HMAC 验签，过短易被在线爆破，强制最小长度
        if kind == "external" and isinstance(secret, str) and secret and len(secret) < 16:
            raise ValueError("external shared secret must be at least 16 characters")
        encrypted_secret: bytes | None = None
        if isinstance(secret, str) and secret:
            encrypted_secret = encrypt_secret(secret_repo or self._services.secret_repo, secret)

        extra = dict(current.extra) if current is not None else {}
        raw_extra = body.get("extra")
        if isinstance(raw_extra, Mapping):
            extra.update({str(key): value for key, value in raw_extra.items()})
        if kind == "feishu":
            region = extra.get("region", "feishu")
            extra = {"region": "lark" if region == "lark" else "feishu"}
        elif kind == "wecom":
            agent_raw = extra.get("agent_id", "")
            agent_id = str(agent_raw).strip() if agent_raw is not None else ""
            extra = {"agent_id": agent_id}
        elif kind == "dingtalk":
            extra = {}

        dashboard_origin = self._nullable_string(body, "dashboard_origin", current)
        if kind in {"feishu", "dingtalk", "wecom"}:
            dashboard_origin = parse_strict_origin(dashboard_origin)
        elif kind == "external":
            # external 无浏览器跳转：强制清空，避免污染 _frontend_base 的回退选择
            dashboard_origin = None

        issuer = self._string(body, "issuer", current, "")
        if kind in {"feishu", "dingtalk", "wecom", "external"}:
            issuer = ""

        default_names = {
            "feishu": "Feishu",
            "dingtalk": "DingTalk",
            "wecom": "WeCom",
            "external": "External SSO",
        }
        provider = self._services.sso_repo.upsert_by_kind(
            kind,
            enabled=bool(body.get("enabled", current.enabled if current else False)),
            display_name=self._string(
                body,
                "display_name",
                current,
                default_names.get(kind, "Octop SSO"),
            ),
            issuer=issuer,
            client_id=self._string(body, "client_id", current, ""),
            client_secret_enc=encrypted_secret,
            scopes=self._string(body, "scopes", current, adapter.default_scopes),
            dashboard_origin=dashboard_origin,
            extra=extra,
        )
        if provider.issuer.strip():
            self._discovery.invalidate(provider.issuer)
        if public_base is not None:
            return self.get_config_for_kind(kind, public_base=public_base)
        return self._provider_config(provider)

    def test_connection(self) -> dict[str, bool | str]:
        return self.test_connection_for_kind("oidc")

    def test_connection_for_kind(self, kind: str) -> dict[str, bool | str]:
        adapter = self._adapter(kind)
        provider = self._services.sso_repo.get_by_kind(kind)
        if provider is None or not adapter.is_configured(provider):
            raise ValueError("SSO is misconfigured")
        return adapter.test_connection(provider)

    def start_login(self, *, redirect_after: str | None, public_base: str) -> dict[str, str]:
        return self.start_login_for_kind(
            "oidc", redirect_after=redirect_after, public_base=public_base
        )

    def start_login_for_kind(
        self,
        kind: str,
        *,
        redirect_after: str | None,
        public_base: str,
        bind_user_id: int | None = None,
    ) -> dict[str, str]:
        self._services.sso_repo.delete_expired()
        adapter = self._adapter(kind)
        provider = self._enabled_provider_for_kind(kind)
        nonce = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(32)
        verifier, challenge = new_pkce_pair()
        redirect_uri = build_redirect_uri(public_base, adapter.callback_path)
        authorization_url = adapter.authorize_url(
            row=provider,
            state=state,
            nonce=nonce,
            code_challenge=challenge,
            redirect_uri=redirect_uri,
        )
        self._services.sso_repo.create_login_state(
            state=state,
            provider_id=provider.id,
            nonce=nonce,
            code_verifier=verifier,
            redirect_after=sanitize_redirect_after(redirect_after),
            expires_at=int(time.time()) + _LOGIN_STATE_TTL_SECONDS,
            user_id=bind_user_id,
        )
        return {
            "authorization_url": authorization_url,
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
        provider = self._services.sso_repo.get_by_id(login_state.provider_id)
        if provider is None or not provider.enabled:
            return self._error_redirect(frontend, "disabled")
        try:
            adapter = self._adapter(provider.kind)
        except ValueError:
            return self._error_redirect(frontend, "misconfigured")
        if not adapter.is_configured(provider) or not code:
            return self._error_redirect(frontend, "misconfigured")

        frontend = self._frontend_base(public_base, provider=provider)
        redirect_uri = build_redirect_uri(public_base, adapter.callback_path)

        try:
            subject, claims = await asyncio.get_running_loop().run_in_executor(
                None,
                partial(
                    adapter.complete_login,
                    code,
                    row=provider,
                    login_state=login_state,
                    redirect_uri=redirect_uri,
                ),
            )
        except jwt.InvalidTokenError:
            logger.exception("SSO callback returned an invalid token (kind=%s)", provider.kind)
            return self._error_redirect(frontend, "invalid_token")
        except (httpx.HTTPError, ValueError):
            logger.exception("SSO callback exchange failed (kind=%s)", provider.kind)
            return self._error_redirect(frontend, "exchange")

        if not subject:
            return self._error_redirect(frontend, "invalid_token")
        try:
            if login_state.user_id is not None:
                user = await self._user_manager.bind_sso_identity(
                    user_id=login_state.user_id,
                    provider_id=provider.id,
                    subject=subject,
                    claims=claims,
                )
            else:
                user = await self._user_manager.resolve_or_create_sso_user(
                    provider_id=provider.id, subject=subject, claims=claims
                )
        except OctopError as exc:
            if exc.code is ErrorCode.USER_DISABLED:
                return self._error_redirect(frontend, "disabled")
            if exc.code is ErrorCode.SSO_IDENTITY_TAKEN:
                return self._error_redirect(frontend, "identity_taken")
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
        params = {"code": login_code, "redirect": login_state.redirect_after}
        if login_state.user_id is not None:
            params["bind"] = "1"
        return RedirectResult(f"{frontend}/login/oidc/complete#{urlencode(params)}")

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

    def issue_browser_login_code(self, *, provider_id: int, user_id: int) -> str:
        """签发一次性浏览器登录码，供同源交接页换 JWT。

        必须新建一行登录态，不能挂到 nonce 占位行上：``attach_login_code`` 会覆盖
        ``expires_at``，若复用 nonce 行会把防重放窗口缩短回登录码 TTL。
        """
        state = secrets.token_urlsafe(32)
        # 登录码 TTL 与占位行过期对齐；attach 会再写一次 expires_at
        expires_at = int(time.time()) + _LOGIN_CODE_TTL_SECONDS
        self._services.sso_repo.create_login_state(
            state=state,
            provider_id=provider_id,
            nonce="",
            code_verifier="",
            redirect_after="",
            expires_at=expires_at,
        )
        login_code = secrets.token_urlsafe(32)
        stored = self._services.sso_repo.attach_login_code(
            state,
            login_code=login_code,
            user_id=user_id,
            expires_at=expires_at,
        )
        # 更新 0 行时关闭失败：不能把未落库的码交给调用方
        if not stored:
            raise RuntimeError("browser login code was not stored")
        return login_code

    async def external_login(
        self,
        *,
        app_id: str,
        username: str,
        timestamp: int,
        nonce: str,
        signature: str,
        display_name: str | None = None,
        email: str | None = None,
    ) -> str:
        """受信外部系统免登：校验 HMAC 后签发一次性浏览器登录码（不是 JWT）。

        浏览器用该码调用 ``POST /api/auth/oidc/exchange`` 换取会话。
        nonce 一经验证通过即被消耗；开户等后续步骤失败时，重试必须更换新的 nonce。

        异常约定：未配置 / 未启用 / 配置不完整 → ``ValueError``；
        身份、签名、时间窗、重放、控制字符校验失败 → ``PermissionError``。
        """
        # 1. external provider 必须已配置并启用
        provider = self._services.sso_repo.get_by_kind("external")
        if (
            provider is None
            or not provider.enabled
            or not self._adapter("external").is_configured(provider)
        ):
            raise ValueError("external SSO is disabled")
        # 签名明文以换行分隔；控制字符会改写字段边界，在拼明文之前拒绝
        if _has_control_char(app_id) or _has_control_char(username) or _has_control_char(nonce):
            raise PermissionError("control characters")
        # 2. app_id 与配置中的 client_id 常量时间比对
        if not secrets.compare_digest(provider.client_id, app_id):
            raise PermissionError("invalid app_id")
        # 3. 时间戳必须在 ±300 秒窗口内，防止旧请求被截获后重用
        now = int(time.time())
        if abs(now - timestamp) > 300:
            raise PermissionError("timestamp out of window")
        # 4. HMAC-SHA256 验签：明文为 ``app_id\nusername\ntimestamp\nnonce``
        # is_configured 已保证密钥存在；显式检查替代 assert，确保 -O 模式下同样收窄
        if provider.client_secret_enc is None:
            raise ValueError("external SSO is misconfigured")
        secret = decrypt_secret(self._services.secret_repo, provider.client_secret_enc)
        message = f"{app_id}\n{username}\n{timestamp}\n{nonce}"
        expected = hmac.new(
            secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not secrets.compare_digest(expected, signature.lower()):
            raise PermissionError("invalid signature")
        # 5. nonce 一次性防重放：先清理过期占位行，再原子插入（唯一约束兜底）。
        # +301：占位行必须活过时间窗；delete_expired 用 expires_at <= now，
        # 未来时间戳（时钟偏差）若只存 now+300，窗口尚未结束行就被删，请求可重放。
        self._services.sso_repo.delete_expired()
        claimed = self._services.sso_repo.claim_once(
            state=nonce,
            provider_id=provider.id,
            expires_at=max(now, timestamp) + 301,
        )
        if not claimed:
            raise PermissionError("nonce replay")
        # 6. 组装 claims，复用既有账号或按默认角色自动开户
        claims: dict[str, Any] = {"sub": username, "preferred_username": username}
        if display_name:
            claims["name"] = display_name
        if email:
            claims["email"] = email
        user = await self._user_manager.resolve_or_create_sso_user(
            provider_id=provider.id, subject=username, claims=claims
        )
        # 7. 审计：actor/target 均为最终登录用户（可能是开户后分配的用户名）
        self._services.audit_repo.write(
            actor=user.username, action="auth.external_login", target=user.username
        )
        # 8. 另起一行签发浏览器登录码，避免覆盖 nonce 行的防重放过期时间
        return self.issue_browser_login_code(provider_id=provider.id, user_id=user.id)

    def _adapter(self, kind: str) -> IdentityProvider:
        adapter = self._adapters.get(kind)
        if adapter is None:
            raise ValueError("unknown SSO provider kind")
        return adapter

    def _enabled_provider(self) -> SsoProviderRow:
        return self._enabled_provider_for_kind("oidc")

    def _enabled_provider_for_kind(self, kind: str) -> SsoProviderRow:
        adapter = self._adapter(kind)
        provider = self._services.sso_repo.get_by_kind(kind)
        if provider is None or not provider.enabled or self._user_manager.count() == 0:
            raise ValueError("SSO is disabled")
        if not adapter.is_configured(provider):
            raise ValueError("SSO is misconfigured")
        return provider

    def _configured_provider(self) -> SsoProviderRow:
        provider = self._services.sso_repo.get_provider()
        adapter = self._adapters["oidc"]
        if provider is None or not adapter.is_configured(provider):
            raise ValueError("SSO is misconfigured")
        return provider

    def _frontend_base(self, public_base: str, *, provider: SsoProviderRow | None = None) -> str:
        if provider is not None and provider.dashboard_origin:
            return provider.dashboard_origin.rstrip("/")
        oidc = self._services.sso_repo.get_by_kind("oidc")
        if oidc is not None and oidc.dashboard_origin:
            return oidc.dashboard_origin.rstrip("/")
        for row in self._services.sso_repo.list():
            if row.enabled and row.dashboard_origin:
                return row.dashboard_origin.rstrip("/")
        return public_base.rstrip("/")

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
        self,
        provider: SsoProviderRow,
        code: str,
        verifier: str,
        public_base: str,
        redirect_uri: str | None = None,
    ) -> dict[str, str]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or build_redirect_uri(public_base),
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
        public_base: str | None = None,
        redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        uri = redirect_uri or build_redirect_uri(public_base or "")
        with self._http_client() as client:
            discovery = self._discovery.get(provider.issuer, httpx_client=client)
            token_endpoint = self._endpoint(discovery, "token_endpoint")
            jwks_uri = self._endpoint(discovery, "jwks_uri")
            token_response = client.post(
                token_endpoint,
                data=self._token_request_data(
                    provider, code, code_verifier, public_base or "", redirect_uri=uri
                ),
            )
            token_response.raise_for_status()
            token = token_response.json()
            id_token = token.get("id_token") if isinstance(token, dict) else None
            if not isinstance(id_token, str):
                raise jwt.InvalidTokenError("token response has no ID token")
            return verify_id_token(
                id_token,
                jwks_uri=jwks_uri,
                issuer=self._endpoint(discovery, "issuer"),
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


def _has_control_char(value: str) -> bool:
    """签名字段是否含 ASCII 控制字符或 DEL（会破坏换行分隔的 HMAC 明文）。"""
    return any(ord(char) < 32 or ord(char) == 127 for char in value)
