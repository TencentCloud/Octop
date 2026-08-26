"""OAuth 2.0 for remote MCP servers via RFC 8414 + dynamic registration.

Issuers and MCP URLs come from the connector catalog
(``oauth_issuer`` + ``mcp_url`` on ``auth_kind=oauth2`` remote entries).
Adding Notion / Ardot / Linear-style connectors is mostly a catalog row.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from octop.infra.connectors.catalog import get_mcp_oauth_remote, mcp_oauth_remote_kinds
from octop.infra.utils.ssrf_guard import (
    UnsafeOutboundUrl,
    host_allowed_for_issuer,
    safe_request,
    validate_https_url,
    validate_https_url_resolved,
)


def mcp_oauth_kinds() -> frozenset[str]:
    return mcp_oauth_remote_kinds()


def issuer_for_kind(kind: str) -> str:
    entry = get_mcp_oauth_remote(kind)
    if entry is None or not entry.oauth_issuer:
        raise ValueError(f"unsupported MCP oauth kind: {kind}")
    return entry.oauth_issuer.rstrip("/")


def resource_for_kind(kind: str) -> str | None:
    """Optional RFC 8707 resource indicator (e.g. Ardot / Dida MCP URL)."""
    entry = get_mcp_oauth_remote(kind)
    if entry is None:
        return None
    resource = (entry.oauth_resource or "").strip()
    return resource or None


async def _ensure_mcp_oauth_url(url: str, *, issuer: str, field: str) -> str:
    """Block SSRF: only public https endpoints under the issuer domain."""
    try:
        validate_https_url(url, field=field)
    except UnsafeOutboundUrl as exc:
        raise ValueError(str(exc)) from exc
    host = (urlparse(url).hostname or "").lower()
    if not host_allowed_for_issuer(host, issuer):
        raise ValueError(f"{field}: host is not allowed for issuer")
    try:
        await validate_https_url_resolved(url, field=field)
    except UnsafeOutboundUrl as exc:
        raise ValueError(str(exc)) from exc
    return url


async def _validate_metadata_endpoints(metadata: dict[str, Any], *, issuer: str) -> dict[str, Any]:
    for key in ("authorization_endpoint", "token_endpoint"):
        await _ensure_mcp_oauth_url(str(metadata[key]), issuer=issuer, field=key)
    reg = metadata.get("registration_endpoint")
    if reg:
        await _ensure_mcp_oauth_url(str(reg), issuer=issuer, field="registration_endpoint")
    return metadata


async def fetch_authorization_metadata(issuer: str) -> dict[str, Any]:
    metadata_url = f"{issuer.rstrip('/')}/.well-known/oauth-authorization-server"
    await _ensure_mcp_oauth_url(metadata_url, issuer=issuer, field="issuer_metadata")
    r = await safe_request("GET", metadata_url, timeout=20.0)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("invalid oauth metadata")
    if not data.get("authorization_endpoint") or not data.get("token_endpoint"):
        raise ValueError("oauth metadata missing endpoints")
    return await _validate_metadata_endpoints(data, issuer=issuer)


async def register_dynamic_client(
    metadata: dict[str, Any],
    *,
    issuer: str,
    redirect_uri: str,
    client_name: str = "Octop Connector",
) -> dict[str, Any]:
    reg_url = metadata.get("registration_endpoint")
    if not reg_url:
        raise ValueError("MCP server does not support dynamic client registration")
    reg_url = await _ensure_mcp_oauth_url(
        str(reg_url), issuer=issuer, field="registration_endpoint"
    )
    auth_methods = metadata.get("token_endpoint_auth_methods_supported") or []
    auth_method = "none" if "none" in auth_methods else "client_secret_post"
    payload = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": auth_method,
    }
    r = await safe_request("POST", reg_url, json=payload, timeout=20.0)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict) or not data.get("client_id"):
        raise ValueError(f"dynamic client registration failed: {data!r}")
    return data


def build_authorize_url(
    metadata: dict[str, Any],
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scope: str | None = None,
    resource: str | None = None,
) -> str:
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if scope:
        params["scope"] = scope
    if resource:
        params["resource"] = resource
    return f"{metadata['authorization_endpoint']}?{urlencode(params)}"


def _http_error_detail(resp: Any) -> str:
    text = ""
    try:
        text = str(getattr(resp, "text", "") or "")[:300]
    except Exception:
        text = ""
    status = getattr(resp, "status_code", "?")
    return f"HTTP {status}" + (f": {text}" if text else "")


async def exchange_authorization_code(
    metadata: dict[str, Any],
    *,
    issuer: str,
    client_id: str,
    client_secret: str | None,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    resource: str | None = None,
) -> dict[str, Any]:
    token_url = await _ensure_mcp_oauth_url(
        str(metadata["token_endpoint"]),
        issuer=issuer,
        field="token_endpoint",
    )
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret
    if resource:
        data["resource"] = resource
    r = await safe_request(
        "POST",
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"token exchange failed ({_http_error_detail(r)})") from exc
    body = r.json()
    if not isinstance(body, dict) or not body.get("access_token"):
        raise ValueError(f"token exchange failed: {body!r}")
    return _normalize_tokens(body)


async def refresh_access_token(
    metadata: dict[str, Any],
    *,
    issuer: str,
    client_id: str,
    client_secret: str | None,
    refresh_token: str,
    resource: str | None = None,
) -> dict[str, Any]:
    token_url = await _ensure_mcp_oauth_url(
        str(metadata["token_endpoint"]),
        issuer=issuer,
        field="token_endpoint",
    )
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    if client_secret:
        data["client_secret"] = client_secret
    if resource:
        data["resource"] = resource
    r = await safe_request(
        "POST",
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"token refresh failed ({_http_error_detail(r)})") from exc
    body = r.json()
    if not isinstance(body, dict) or not body.get("access_token"):
        raise ValueError(f"token refresh failed: {body!r}")
    return _normalize_tokens(body, fallback_refresh=refresh_token)


def _normalize_tokens(
    body: dict[str, Any],
    *,
    fallback_refresh: str | None = None,
) -> dict[str, Any]:
    expires_in = int(body.get("expires_in") or 0)
    expires_at = int(time.time()) + expires_in if expires_in else None
    out: dict[str, Any] = {
        "access_token": str(body["access_token"]),
        "refresh_token": str(body.get("refresh_token") or fallback_refresh or ""),
        "expires_at": expires_at,
    }
    if body.get("token_type"):
        out["token_type"] = str(body["token_type"])
    return out
