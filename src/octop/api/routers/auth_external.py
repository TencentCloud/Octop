"""受信外部系统服务器间免登接口（HMAC-SHA256 签名换 JWT）。

外部系统已自行完成用户认证，使用与本机共享的密钥对约定明文
``f"{app_id}\n{username}\n{timestamp}\n{nonce}"`` 计算 HMAC-SHA256（hex），
携带 ``app_id`` / ``username`` / ``timestamp`` / ``nonce`` / ``signature``
调用本接口换取与 ``/api/auth/login`` 结构一致的 JWT 响应；
用户不存在时按默认角色自动开户。配置（app_id 与共享密钥）通过
``GET/PUT /api/oauth/providers/external`` 管理。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from octop.api.common.client_ip import resolve_client_ip
from octop.api.deps import get_server, sign_token
from octop.api.routers.auth import _raise_if_throttled, _user_json
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()


class ExternalExchangeBody(BaseModel):
    """外部系统免登换票请求体。"""

    app_id: str = Field(min_length=1, max_length=128, description="外部系统应用标识")
    username: str = Field(min_length=1, max_length=128, description="外部系统已认证的用户名")
    timestamp: int = Field(description="Unix 秒时间戳，须在服务器时间 ±300 秒内")
    nonce: str = Field(min_length=8, max_length=128, description="一次性随机串，防重放")
    signature: str = Field(min_length=64, max_length=64, description="HMAC-SHA256 hex 签名")
    display_name: str | None = Field(
        default=None, max_length=128, description="显示名（开户时写入）"
    )
    email: str | None = Field(default=None, max_length=254, description="邮箱（开户/更新时写入）")


@router.post(
    "/external/exchange",
    summary="External trusted SSO exchange",
    description=(
        "受信外部系统免登换票：无需鉴权，外部系统以共享密钥的 HMAC-SHA256 签名换取 "
        "Octop JWT。时间戳须在 ±300 秒窗口内，nonce 一次性有效（重放即拒绝）；"
        "用户不存在时按默认角色自动开户。响应结构与 /api/auth/login 一致。"
    ),
)
async def external_exchange(
    body: ExternalExchangeBody, request: Request, server: Any = Depends(get_server)
) -> dict[str, Any]:
    # 匿名失败节流（与 LDAP bind 同一实现，键为 username + 解析后的客户端 IP）：
    # 进入即检查，锁定期间直接 429，避免对共享密钥的在线爆破与失败审计放大。
    throttle = server.external_login_throttle
    client_ip = resolve_client_ip(request)
    _raise_if_throttled(throttle.retry_after(body.username, client_ip))
    # 校验全部在 infra 层完成：ValueError=未配置/未启用/配置不完整（配置问题，
    # 不计入爆破预算），PermissionError=身份/签名/时间窗/重放失败，OctopError 原样向上传播。
    try:
        user = await server.sso_service.external_login(
            app_id=body.app_id,
            username=body.username,
            timestamp=body.timestamp,
            nonce=body.nonce,
            signature=body.signature,
            display_name=body.display_name,
            email=body.email,
        )
    except ValueError as exc:
        raise OctopError.localized(ErrorCode.OIDC_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        # 验签失败计入节流预算并写失败审计后再返回 401
        throttle.record_failure(body.username, client_ip)
        server.services.audit_repo.write(
            actor=body.username, action="auth.external_failed", target=body.username
        )
        raise OctopError(ErrorCode.AUTH_FAILED, str(exc)) from exc
    # 成功后清除该 (username, IP) 的失败计数（IP 维度计数按节流实现保留）
    throttle.clear(body.username, client_ip)
    # 成功响应与 /api/auth/login 保持一致
    secret = server.services.secret_repo.get("jwt")
    ttl = server.services.config.access_token_ttl_seconds
    return {
        "access_token": sign_token(
            secret, sub=user.id, uname=user.username, role=user.role, ttl_seconds=ttl
        ),
        "token_type": "Bearer",
        "expires_in": ttl,
        "user": _user_json(user, locale=user.locale),
    }
