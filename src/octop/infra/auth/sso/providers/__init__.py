"""Dashboard SSO identity-provider adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from octop.infra.auth.sso.providers.base import SSO_KINDS, IdentityProvider

if TYPE_CHECKING:
    from octop.infra.auth.sso.service import SsoService


def build_adapters(service: SsoService) -> dict[str, IdentityProvider]:
    from octop.infra.auth.sso.providers.dingtalk import DingTalkAdapter
    from octop.infra.auth.sso.providers.external import ExternalAdapter
    from octop.infra.auth.sso.providers.feishu import FeishuAdapter
    from octop.infra.auth.sso.providers.oidc import OidcAdapter
    from octop.infra.auth.sso.providers.wecom import WeComAdapter

    return {
        "oidc": OidcAdapter(service),
        "feishu": FeishuAdapter(service),
        "dingtalk": DingTalkAdapter(service),
        "wecom": WeComAdapter(service),
        # 受信外部系统免登：无 service 依赖，不进 SSO_KINDS（不出现在登录页按钮）。
        "external": ExternalAdapter(),
    }


__all__ = ["SSO_KINDS", "IdentityProvider", "build_adapters"]
