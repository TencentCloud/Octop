"""Connector OAuth flows — per-vendor modules + :mod:`registry` dispatcher."""

from octop.infra.connectors.oauth.registry import (
    auth_info_for_kind,
    authorize_url_for_paste,
    delete_oauth_ctx,
    exchange_oauth_code,
    exchange_pasted_auth_code,
    load_oauth_ctx,
    oauth_mode_for_kind,
    oauth_ready_for_kind,
    oauth_supported_kinds,
    refresh_oauth_credentials,
    save_oauth_ctx,
    start_oauth,
    start_oauth_for_target,
)

__all__ = [
    "auth_info_for_kind",
    "authorize_url_for_paste",
    "delete_oauth_ctx",
    "exchange_oauth_code",
    "exchange_pasted_auth_code",
    "load_oauth_ctx",
    "oauth_mode_for_kind",
    "oauth_ready_for_kind",
    "oauth_supported_kinds",
    "refresh_oauth_credentials",
    "save_oauth_ctx",
    "start_oauth",
    "start_oauth_for_target",
]
