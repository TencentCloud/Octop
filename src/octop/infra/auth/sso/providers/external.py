"""受信外部系统服务器间免登适配器（External SSO）。

配置语义（复用 sso_providers 表字段）：
- ``client_id`` 存外部系统的应用标识（app_id），免登请求必须携带相同值；
- ``client_secret_enc`` 存加密后的 HMAC-SHA256 共享密钥，用于校验请求签名。

该适配器不参与浏览器跳转登录，仅服务于
``POST /api/auth/external/exchange`` 的服务器间签名换票流程，因此刻意不加入
``SSO_KINDS``，登录页按钮列表（providers_status）不会展示它。
"""

from __future__ import annotations

from typing import Any

from octop.infra.db.repos.sso import SsoLoginStateRow, SsoProviderRow


class ExternalAdapter:
    """受信外部系统适配器：验签逻辑在 ``SsoService.external_login`` 中完成。"""

    kind = "external"
    # 占位回调路径：满足 IdentityProvider 协议并让管理接口能展示 redirect_uri，
    # 实际不会被调用（external 没有浏览器回调）。
    callback_path = "/api/auth/external/callback"
    default_scopes = ""

    def is_configured(self, row: SsoProviderRow) -> bool:
        """配置完整的判定：app_id 非空且已设置加密的共享密钥。"""
        return bool(row.client_id.strip()) and row.client_secret_enc is not None

    def authorize_url(
        self,
        *,
        row: SsoProviderRow,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str:
        """external 无浏览器授权页，任何调用都视为误用。"""
        raise ValueError("external provider does not support browser login")

    def complete_login(
        self,
        code: str,
        *,
        row: SsoProviderRow,
        login_state: SsoLoginStateRow,
        redirect_uri: str,
    ) -> tuple[str, dict[str, Any]]:
        """external 无授权码换 token 流程，任何调用都视为误用。"""
        raise ValueError("external provider does not support browser login")

    def test_connection(self, row: SsoProviderRow) -> dict[str, bool | str]:
        """共享密钥保存在本机，没有外部探测目标，配置完整即视为可用。"""
        return {"ok": True}
