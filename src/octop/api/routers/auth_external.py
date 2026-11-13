"""受信外部系统服务器间免登接口（HMAC-SHA256 签名换一次性登录码）。

外部系统已自行完成用户认证，使用与本机共享的密钥对约定明文
``f"{app_id}\\n{username}\\n{timestamp}\\n{nonce}"`` 计算 HMAC-SHA256（hex），
携带 ``app_id`` / ``username`` / ``timestamp`` / ``nonce`` / ``signature``
调用本接口换取短时一次性登录码（不是 JWT）。共享密钥加密存放在服务端，
由 Octop 管理员与外部系统运维共同持有，可在管理 → 用户中更新 external
提供商密钥来轮换（旧签名立即失效）。

外部系统拿到 ``login_code`` 后，把用户浏览器重定向到
``/login/external#code=<login_code>&redirect=<站内路径>``。交接页只从 hash
读取一次性码，再调用 ``POST /api/auth/oidc/exchange`` 换取会话。不要把
``access_token`` 放进 URL。配置（app_id 与共享密钥）通过
``GET/PUT /api/oauth/providers/external`` 管理。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from octop.api.common.client_ip import resolve_client_ip
from octop.api.deps import get_server
from octop.api.routers.auth import _raise_if_throttled
from octop.infra.auth.sso.service import LOGIN_CODE_TTL_SECONDS
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()
logger = logging.getLogger(__name__)

# 拒绝换行等控制字符，避免改写 HMAC 明文的字段边界
_NO_CONTROL = r"^[^\x00-\x1f\x7f]+$"

# PermissionError 文本是本模块控制的固定标记，映射为审计原因码，不回传给调用方
_FAILURE_REASONS = {
    "invalid app_id": "bad_app_id",
    "invalid signature": "bad_signature",
    "timestamp out of window": "stale_timestamp",
    "nonce replay": "nonce_replay",
    "control characters": "bad_request",
}


class ExternalExchangeBody(BaseModel):
    """外部系统免登换票请求体。"""

    app_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=_NO_CONTROL,
        description="外部系统应用标识",
    )
    username: str = Field(
        min_length=1,
        max_length=128,
        pattern=_NO_CONTROL,
        description="外部系统已认证的用户名",
    )
    timestamp: int = Field(description="Unix 秒时间戳，须在服务器时间 ±300 秒内")
    nonce: str = Field(
        min_length=8,
        max_length=128,
        pattern=_NO_CONTROL,
        description="一次性随机串，防重放",
    )
    signature: str = Field(min_length=64, max_length=64, description="HMAC-SHA256 hex 签名")
    display_name: str | None = Field(
        default=None, max_length=128, description="显示名（开户时写入）"
    )
    email: str | None = Field(default=None, max_length=254, description="邮箱（开户/更新时写入）")


def _failure_reason(exc: PermissionError) -> str:
    """把固定的 PermissionError 标记映射为稳定审计原因码，不回传用户输入。"""
    return _FAILURE_REASONS.get(str(exc), "bad_request")


@router.post(
    "/external/exchange",
    summary="External trusted SSO exchange",
    description=(
        "受信外部系统免登换票：无需鉴权，外部系统以共享密钥的 HMAC-SHA256 签名换取 "
        "短时一次性登录码（login_code，默认 60 秒），不是 JWT。共享密钥加密存放在服务端，"
        "由 Octop 管理员与外部系统运维共同持有，可在管理 → 用户中更新 external 提供商密钥轮换"
        "（旧签名立即失效）。时间戳须在 ±300 秒窗口内，nonce 一次性有效（重放即拒绝）；"
        "用户不存在时按默认角色自动开户。外部系统应将浏览器重定向到 "
        "/login/external#code=<login_code>&redirect=<站内路径>，交接页再调用 "
        "POST /api/auth/oidc/exchange 换取会话。不要把 access_token 放进 URL。"
    ),
)
async def external_exchange(
    body: ExternalExchangeBody, request: Request, server: Any = Depends(get_server)
) -> dict[str, Any]:
    """校验 HMAC 后返回一次性登录码；失败原因只写日志与审计，不返回给匿名调用方。"""
    # 匿名失败节流（与 LDAP bind 同一实现，键为 username + 解析后的客户端 IP）：
    # 进入即检查，锁定期间直接 429，避免对共享密钥的在线爆破与失败审计放大。
    throttle = server.external_login_throttle
    client_ip = resolve_client_ip(request)
    _raise_if_throttled(throttle.retry_after(body.username, client_ip))
    # 校验全部在 infra 层完成：ValueError=未配置/未启用/配置不完整（配置问题，
    # 不计入爆破预算），PermissionError=身份/签名/时间窗/重放失败，OctopError 原样向上传播。
    try:
        login_code = await server.sso_service.external_login(
            app_id=body.app_id,
            username=body.username,
            timestamp=body.timestamp,
            nonce=body.nonce,
            signature=body.signature,
            display_name=body.display_name,
            email=body.email,
        )
    except ValueError as exc:
        # 配置问题不计入节流；对外与验签失败同一响应，避免匿名调用方区分原因
        logger.info("external login rejected: %s", exc)
        reason = "misconfigured" if "misconfigured" in str(exc) else "disabled"
        server.services.audit_repo.write(
            actor=body.username,
            action="auth.external_failed",
            target=body.username,
            payload=reason,
        )
        raise OctopError.localized(ErrorCode.AUTH_FAILED) from exc
    except PermissionError as exc:
        # 验签失败计入节流预算；具体原因只进服务端日志和稳定审计码
        logger.info("external login rejected: %s", exc)
        throttle.record_failure(body.username, client_ip)
        server.services.audit_repo.write(
            actor=body.username,
            action="auth.external_failed",
            target=body.username,
            payload=_failure_reason(exc),
        )
        raise OctopError.localized(ErrorCode.AUTH_FAILED) from exc
    # 成功后清除该 (username, IP) 的失败计数（IP 维度计数按节流实现保留）
    throttle.clear(body.username, client_ip)
    return {"login_code": login_code, "expires_in": LOGIN_CODE_TTL_SECONDS}
