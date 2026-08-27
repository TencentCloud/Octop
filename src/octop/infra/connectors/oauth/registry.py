"""Dispatch connector OAuth flows by kind."""

from __future__ import annotations

import json
from typing import Any

from octop.infra.connectors.catalog import get_catalog_entry, get_mcp_oauth_remote
from octop.infra.connectors.custom_mcp import CUSTOM_MCP_KIND
from octop.infra.connectors.oauth.discovery import discover_oauth_from_mcp_url
from octop.infra.connectors.oauth.mcp import (
    build_authorize_url,
    exchange_authorization_code,
    fetch_authorization_metadata,
    issuer_for_kind,
    mcp_oauth_kinds,
    refresh_access_token,
    register_dynamic_client,
    resource_for_kind,
)
from octop.infra.connectors.oauth.pkce import new_pkce_pair

OAUTH_CTX_PREFIX = "connector.oauth.ctx."

_AUTH_CODE_PASSTHROUGH_KINDS: frozenset[str] = frozenset()


def _scope_from_metadata(metadata: dict[str, Any]) -> str | None:
    scopes = metadata.get("scopes_supported")
    if isinstance(scopes, list) and scopes:
        return " ".join(str(s) for s in scopes if s)
    return None


def _scopes_for_kind(kind: str, metadata: dict[str, Any]) -> str | None:
    """Prefer AS metadata scopes; fall back to catalog ``oauth_scopes``."""
    from_meta = _scope_from_metadata(metadata)
    if from_meta:
        return from_meta
    entry = get_mcp_oauth_remote(kind)
    if entry is None:
        return None
    scopes = (entry.oauth_scopes or "").strip()
    return scopes or None


def oauth_supported_kinds() -> frozenset[str]:
    return mcp_oauth_kinds() | _AUTH_CODE_PASSTHROUGH_KINDS


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
    if get_mcp_oauth_remote(kind) is not None:
        return True
    return kind in _AUTH_CODE_PASSTHROUGH_KINDS


def oauth_mode_for_kind(kind: str) -> str | None:
    if get_mcp_oauth_remote(kind) is not None:
        return "dynamic"
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


async def _start_mcp_oauth_from_discovery(
    *,
    flow: str,
    kind: str,
    redirect_uri: str,
    state: str,
    issuer: str,
    resource: str | None,
    metadata: dict[str, Any],
    server_name: str | None = None,
    mcp_url: str | None = None,
    scope: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    verifier, challenge = new_pkce_pair()
    reg = await register_dynamic_client(metadata, issuer=issuer, redirect_uri=redirect_uri)
    client_id = str(reg["client_id"])
    client_secret = str(reg.get("client_secret") or "") or None
    url = build_authorize_url(
        metadata,
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=challenge,
        scope=scope,
        resource=resource,
    )
    ctx: dict[str, Any] = {
        "flow": flow,
        "kind": kind,
        "metadata": metadata,
        "client_id": client_id,
        "client_secret": client_secret,
        "resource": resource,
        "redirect_uri": redirect_uri,
        "issuer": issuer,
    }
    if server_name:
        ctx["server_name"] = server_name
    if mcp_url:
        ctx["mcp_url"] = mcp_url
    return url, verifier, ctx


async def start_oauth(
    *,
    kind: str,
    redirect_uri: str,
    state: str,
    settings_repo: Any,
) -> tuple[str, str, dict[str, Any]]:
    """Return authorize_url, code_verifier, ctx for a catalog connector kind."""
    del settings_repo
    if kind not in mcp_oauth_kinds():
        raise ValueError(f"oauth not supported for {kind}")
    issuer = issuer_for_kind(kind)
    metadata = await fetch_authorization_metadata(issuer)
    resource = resource_for_kind(kind)
    return await _start_mcp_oauth_from_discovery(
        flow="mcp",
        kind=kind,
        redirect_uri=redirect_uri,
        state=state,
        issuer=issuer,
        resource=resource,
        metadata=metadata,
        scope=_scopes_for_kind(kind, metadata),
    )


async def start_oauth_for_target(
    *,
    target: dict[str, Any],
    redirect_uri: str,
    state: str,
    settings_repo: Any,
    mcp_url: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Unified OAuth start for catalog connectors and custom MCP servers."""
    target_type = str(target.get("type") or "").strip()
    if target_type == "catalog":
        kind = str(target.get("kind") or "").strip()
        if not kind:
            raise ValueError("catalog target requires kind")
        return await start_oauth(
            kind=kind,
            redirect_uri=redirect_uri,
            state=state,
            settings_repo=settings_repo,
        )
    if target_type == "custom_mcp":
        server_name = str(target.get("server_name") or "").strip()
        url = str(mcp_url or target.get("mcp_url") or "").strip()
        if not server_name:
            raise ValueError("custom_mcp target requires server_name")
        if not url:
            raise ValueError("custom MCP server url is required; save the server first")
        return await start_custom_mcp_oauth(
            server_name=server_name,
            mcp_url=url,
            redirect_uri=redirect_uri,
            state=state,
        )
    raise ValueError(f"unsupported oauth target type: {target_type!r}")


def oauth_state_kind_for_target(target: dict[str, Any]) -> str:
    target_type = str(target.get("type") or "").strip()
    if target_type == "catalog":
        return str(target.get("kind") or "").strip()
    if target_type == "custom_mcp":
        return CUSTOM_MCP_KIND
    raise ValueError(f"unsupported oauth target type: {target_type!r}")


def oauth_target_requires_https(target: dict[str, Any]) -> bool:
    target_type = str(target.get("type") or "").strip()
    if target_type == "catalog":
        kind = str(target.get("kind") or "").strip()
        return get_mcp_oauth_remote(kind) is not None
    return target_type == "custom_mcp"


async def start_custom_mcp_oauth(
    *,
    server_name: str,
    mcp_url: str,
    redirect_uri: str,
    state: str,
    discovery: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Start OAuth for a user-defined MCP server (issuer discovered from MCP URL)."""
    found = discovery if discovery is not None else await discover_oauth_from_mcp_url(mcp_url)
    if not found.get("available"):
        raise ValueError(str(found.get("error") or "OAuth not available for this MCP URL"))
    issuer = str(found["issuer"])
    resource = str(found.get("resource") or "").strip() or None
    metadata = found.get("metadata")
    if not isinstance(metadata, dict):
        metadata = await fetch_authorization_metadata(issuer)
    scopes_raw = metadata.get("scopes_supported")
    scope = (
        " ".join(str(s) for s in scopes_raw if s)
        if isinstance(scopes_raw, list) and scopes_raw
        else None
    )
    return await _start_mcp_oauth_from_discovery(
        flow="custom_mcp",
        kind=CUSTOM_MCP_KIND,
        redirect_uri=redirect_uri,
        state=state,
        issuer=issuer,
        resource=resource,
        metadata=metadata,
        server_name=server_name,
        mcp_url=mcp_url,
        scope=scope,
    )


async def refresh_custom_mcp_oauth(oauth: dict[str, Any]) -> dict[str, Any]:
    refresh = str(oauth.get("refresh_token") or "").strip()
    issuer = str(oauth.get("oauth_issuer") or "").strip()
    client_id = str(oauth.get("oauth_client_id") or "").strip()
    if not refresh or not issuer or not client_id:
        return oauth
    metadata = await fetch_authorization_metadata(issuer)
    client_secret_raw = oauth.get("oauth_client_secret")
    secret = str(client_secret_raw) if client_secret_raw else None
    resource = str(oauth.get("oauth_resource") or "").strip() or None
    refreshed = await refresh_access_token(
        metadata,
        issuer=issuer,
        client_id=client_id,
        client_secret=secret,
        refresh_token=refresh,
        resource=resource,
    )
    merged = dict(oauth)
    merged.update(refreshed)
    return merged


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

    if flow == "custom_mcp":
        metadata = ctx.get("metadata")
        if not isinstance(metadata, dict):
            issuer = str(ctx.get("issuer") or "")
            if not issuer:
                raise ValueError("missing custom MCP oauth issuer")
            metadata = await fetch_authorization_metadata(issuer)
        client_id = str(ctx.get("client_id") or "")
        client_secret_raw = ctx.get("client_secret")
        secret = str(client_secret_raw) if client_secret_raw else None
        if not client_id:
            raise ValueError("missing custom MCP oauth client_id")
        resource = str(ctx.get("resource") or "") or None
        exchange_redirect = str(ctx.get("redirect_uri") or "").strip() or redirect_uri
        issuer = str(ctx.get("issuer") or "")
        return await exchange_authorization_code(
            metadata,
            issuer=issuer,
            client_id=client_id,
            client_secret=secret,
            code=code,
            redirect_uri=exchange_redirect,
            code_verifier=code_verifier,
            resource=resource,
        )

    if flow == "mcp" or kind in mcp_oauth_kinds():
        metadata = ctx.get("metadata")
        if not isinstance(metadata, dict):
            metadata = await fetch_authorization_metadata(issuer_for_kind(kind))
        client_id = str(ctx.get("client_id") or "")
        client_secret_raw = ctx.get("client_secret")
        secret = str(client_secret_raw) if client_secret_raw else None
        if not client_id:
            raise ValueError("missing MCP oauth client_id")
        resource = str(ctx.get("resource") or "") or resource_for_kind(kind)
        # Prefer the redirect_uri used at authorize/register time — Host header
        # drift (localhost vs 127.0.0.1) would otherwise fail the exchange.
        exchange_redirect = str(ctx.get("redirect_uri") or "").strip() or redirect_uri
        return await exchange_authorization_code(
            metadata,
            issuer=issuer_for_kind(kind),
            client_id=client_id,
            client_secret=secret,
            code=code,
            redirect_uri=exchange_redirect,
            code_verifier=code_verifier,
            resource=resource,
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
            resource=resource_for_kind(kind),
        )

    return creds
