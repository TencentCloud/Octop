"""Dispatch connector OAuth flows by kind."""

from __future__ import annotations

import json
from typing import Any

from octop.infra.connectors.catalog import get_catalog_entry
from octop.infra.connectors.oauth.mcp import (
    build_authorize_url,
    exchange_authorization_code,
    fetch_authorization_metadata,
    issuer_for_kind,
    mcp_oauth_kinds,
    refresh_access_token,
    register_dynamic_client,
)
from octop.infra.connectors.oauth.pkce import new_pkce_pair

OAUTH_CTX_PREFIX = "connector.oauth.ctx."

_BUILTIN_OAUTH_KINDS = frozenset({"notion"})

_AUTH_CODE_PASSTHROUGH_KINDS: frozenset[str] = frozenset()


def oauth_supported_kinds() -> frozenset[str]:
    return _BUILTIN_OAUTH_KINDS


def save_oauth_ctx(settings_repo: Any, state_id: str, ctx: dict[str, Any]) -> None:
    settings_repo.set(f"{OAUTH_CTX_PREFIX}{state_id}", json.dumps(ctx))


def load_oauth_ctx(settings_repo: Any, state_id: str) -> dict[str, Any]:
    raw = settings_repo.get(f"{OAUTH_CTX_PREFIX}{state_id}")
    if not raw:
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def delete_oauth_ctx(settings_repo: Any, state_id: str) -> None:
    settings_repo.delete(f"{OAUTH_CTX_PREFIX}{state_id}")


def oauth_ready_for_kind(kind: str, settings_repo: Any) -> bool:
    del settings_repo
    if kind == "notion":
        return True
    return kind in _AUTH_CODE_PASSTHROUGH_KINDS


def oauth_mode_for_kind(kind: str) -> str | None:
    if kind == "notion":
        return "dynamic"
    if kind in _BUILTIN_OAUTH_KINDS:
        return "configured"
    return None


def authorize_url_for_paste(kind: str, settings_repo: Any) -> str | None:
    del settings_repo
    entry = get_catalog_entry(kind)
    return entry.quick_auth_url if entry else None


def auth_info_for_kind(kind: str, settings_repo: Any) -> dict[str, str | None]:
    entry = get_catalog_entry(kind)
    if entry is None:
        return {
            "authorize_url": None,
            "login_url": None,
            "guide_url": None,
            "manual_url": None,
            "auth_hint": None,
        }
    return {
        "authorize_url": authorize_url_for_paste(kind, settings_repo),
        "login_url": entry.login_url,
        "guide_url": entry.guide_url or entry.doc_url,
        "manual_url": entry.manual_url or entry.guide_url or entry.doc_url,
        "auth_hint": entry.auth_hint,
    }


async def exchange_pasted_auth_code(
    *,
    kind: str,
    code: str,
    settings_repo: Any,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Exchange a user-pasted authorization code (QClaw-style copy-paste flow)."""
    del settings_repo, extra
    code = code.strip()
    if not code:
        raise ValueError("授权码不能为空")

    if kind in _AUTH_CODE_PASSTHROUGH_KINDS:
        return {"cookie": code}

    raise ValueError(f"auth code exchange not supported for {kind}")


async def start_oauth(
    *,
    kind: str,
    redirect_uri: str,
    state: str,
    settings_repo: Any,
) -> tuple[str, str, dict[str, Any]]:
    """Return authorize_url, code_verifier, ctx to persist for callback."""
    del settings_repo
    verifier, challenge = new_pkce_pair()

    if kind in mcp_oauth_kinds():
        issuer = issuer_for_kind(kind)
        metadata = await fetch_authorization_metadata(issuer)
        reg = await register_dynamic_client(metadata, issuer=issuer, redirect_uri=redirect_uri)
        client_id = str(reg["client_id"])
        client_secret = str(reg.get("client_secret") or "") or None
        url = build_authorize_url(
            metadata,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=challenge,
        )
        ctx = {
            "flow": "mcp",
            "kind": kind,
            "metadata": metadata,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        return url, verifier, ctx

    raise ValueError(f"oauth not supported for {kind}")


async def exchange_oauth_code(
    *,
    kind: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    settings_repo: Any,
    state_id: str,
) -> dict[str, Any]:
    ctx = load_oauth_ctx(settings_repo, state_id)
    flow = ctx.get("flow")

    if flow == "mcp" or kind in mcp_oauth_kinds():
        metadata = ctx.get("metadata")
        if not isinstance(metadata, dict):
            metadata = await fetch_authorization_metadata(issuer_for_kind(kind))
        client_id = str(ctx.get("client_id") or "")
        client_secret_raw = ctx.get("client_secret")
        secret = str(client_secret_raw) if client_secret_raw else None
        if not client_id:
            raise ValueError("missing MCP oauth client_id")
        return await exchange_authorization_code(
            metadata,
            issuer=issuer_for_kind(kind),
            client_id=client_id,
            client_secret=secret,
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )

    raise ValueError(f"oauth exchange not supported for {kind}")


async def refresh_oauth_credentials(
    *,
    kind: str,
    creds: dict[str, Any],
    settings_repo: Any,
) -> dict[str, Any]:
    del settings_repo
    refresh = str(creds.get("refresh_token") or "")
    if not refresh:
        return creds

    if kind in mcp_oauth_kinds():
        issuer = issuer_for_kind(kind)
        metadata = await fetch_authorization_metadata(issuer)
        client_id = str(creds.get("oauth_client_id") or "")
        client_secret_raw = creds.get("oauth_client_secret")
        secret = str(client_secret_raw) if client_secret_raw else None
        if not client_id:
            return creds
        return await refresh_access_token(
            metadata,
            issuer=issuer,
            client_id=client_id,
            client_secret=secret,
            refresh_token=refresh,
        )

    return creds
