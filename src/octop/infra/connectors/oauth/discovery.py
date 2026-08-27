"""Discover MCP OAuth issuers from a remote MCP URL (RFC 9728 + MCP authorization)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from octop.infra.connectors.oauth.mcp import fetch_authorization_metadata
from octop.infra.utils.ssrf_guard import UnsafeOutboundUrl, safe_request, validate_https_url

_RESOURCE_METADATA_PARAM = re.compile(
    r'resource_metadata\s*=\s*"([^"]+)"',
    re.IGNORECASE,
)


def _mcp_url_host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().rstrip(".")


def _is_loopback_mcp_url(url: str) -> bool:
    host = _mcp_url_host(url)
    return host in {"localhost", "127.0.0.1", "::1"}


def build_protected_resource_metadata_urls(
    mcp_url: str,
    *,
    www_auth_resource_metadata: str | None = None,
) -> list[str]:
    """Ordered PRM discovery URLs per MCP authorization / RFC 9728."""
    urls: list[str] = []
    if www_auth_resource_metadata:
        urls.append(www_auth_resource_metadata.strip())
    parsed = urlparse(mcp_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or ""
    if path and path != "/":
        urls.append(urljoin(base, f"/.well-known/oauth-protected-resource{path}"))
    urls.append(urljoin(base, "/.well-known/oauth-protected-resource"))
    # De-dupe while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for item in urls:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def parse_www_authenticate_resource_metadata(header_value: str | None) -> str | None:
    if not header_value:
        return None
    match = _RESOURCE_METADATA_PARAM.search(header_value)
    if not match:
        return None
    return match.group(1).strip() or None


async def _fetch_prm_document(url: str) -> dict[str, Any] | None:
    try:
        validate_https_url(url, field="resource_metadata")
    except UnsafeOutboundUrl:
        return None
    try:
        resp = await safe_request("GET", url, timeout=15.0)
    except Exception:
        return None
    if resp.status_code >= 400:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    servers = data.get("authorization_servers")
    if not isinstance(servers, list) or not servers:
        return None
    return data


async def _probe_401_resource_metadata(mcp_url: str) -> str | None:
    """Unauthenticated MCP initialize may return WWW-Authenticate with PRM URL."""
    parsed = urlparse(mcp_url)
    if parsed.scheme not in ("http", "https"):
        return None
    if _is_loopback_mcp_url(mcp_url):
        return None
    if parsed.scheme != "https":
        return None
    try:
        validate_https_url(mcp_url, field="mcp_url")
    except UnsafeOutboundUrl:
        return None
    try:
        resp = await safe_request(
            "POST",
            mcp_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "octop", "version": "0.1"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
            timeout=15.0,
        )
    except Exception:
        return None
    if resp.status_code not in (401, 403):
        return None
    return parse_www_authenticate_resource_metadata(resp.headers.get("WWW-Authenticate"))


def _normalize_issuer(raw: str, *, mcp_url: str) -> str:
    text = raw.strip().rstrip("/")
    if text.startswith("http://") or text.startswith("https://"):
        return text
    base = f"{urlparse(mcp_url).scheme}://{urlparse(mcp_url).netloc}"
    return urljoin(base, text).rstrip("/")


async def discover_oauth_from_mcp_url(mcp_url: str) -> dict[str, Any]:
    """Return OAuth discovery details for a remote MCP HTTP endpoint.

    Result shape::

        {
          "available": bool,
          "issuer": str | None,
          "resource": str | None,
          "metadata": dict | None,  # AS metadata when available
          "scopes_supported": list[str] | None,
          "error": str | None,
        }
    """
    url = mcp_url.strip()
    if not url:
        return {"available": False, "error": "empty mcp url"}
    if _is_loopback_mcp_url(url):
        return {"available": False, "error": "loopback MCP does not use remote OAuth"}

    www_auth_prm = await _probe_401_resource_metadata(url)
    prm_doc: dict[str, Any] | None = None
    for candidate in build_protected_resource_metadata_urls(
        url,
        www_auth_resource_metadata=www_auth_prm,
    ):
        prm_doc = await _fetch_prm_document(candidate)
        if prm_doc is not None:
            break

    if prm_doc is None:
        return {"available": False, "error": "protected resource metadata not found"}

    resource = str(prm_doc.get("resource") or "").strip() or url
    servers = prm_doc.get("authorization_servers")
    if not isinstance(servers, list) or not servers:
        return {"available": False, "error": "authorization_servers missing"}

    issuer = _normalize_issuer(str(servers[0]), mcp_url=url)
    try:
        metadata = await fetch_authorization_metadata(issuer)
    except Exception as exc:
        return {"available": False, "error": str(exc), "issuer": issuer, "resource": resource}

    if not metadata.get("registration_endpoint"):
        return {
            "available": False,
            "error": "authorization server does not support dynamic client registration",
            "issuer": issuer,
            "resource": resource,
        }

    scopes_raw = metadata.get("scopes_supported")
    scopes = [str(s) for s in scopes_raw if s] if isinstance(scopes_raw, list) else None
    return {
        "available": True,
        "issuer": issuer,
        "resource": resource,
        "metadata": metadata,
        "scopes_supported": scopes,
        "error": None,
    }
