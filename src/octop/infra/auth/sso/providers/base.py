"""Identity-provider adapter contract for dashboard SSO."""

from __future__ import annotations

from typing import Any, Protocol

from octop.infra.db.repos.sso import SsoLoginStateRow, SsoProviderRow

SSO_KINDS = ("oidc", "feishu", "dingtalk", "wecom")
DEFAULT_OAUTH_CALLBACK_PATH = "/api/auth/oauth/callback"


class IdentityProvider(Protocol):
    kind: str
    callback_path: str
    default_scopes: str

    def is_configured(self, row: SsoProviderRow) -> bool: ...

    def authorize_url(
        self,
        *,
        row: SsoProviderRow,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str: ...

    def complete_login(
        self,
        code: str,
        *,
        row: SsoProviderRow,
        login_state: SsoLoginStateRow,
        redirect_uri: str,
    ) -> tuple[str, dict[str, Any]]: ...

    def test_connection(self, row: SsoProviderRow) -> dict[str, bool | str]: ...
