"""User-defined MCP servers (streamable_http / stdio) stored as one connector doc."""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

from octop.infra.utils.ssrf_guard import UnsafeOutboundUrl, validate_https_url

CUSTOM_MCP_KIND = "custom-mcp"
CUSTOM_MCP_DISPLAY_NAME = "自定义 MCP"

_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_META_KEYS = frozenset({"enabled", "display_name", "default_open"})
_OAUTH_KEY = "oauth"
_SECRET_KEYS = frozenset({_OAUTH_KEY})
_HARNESS_STRIP_KEYS = _META_KEYS | _SECRET_KEYS
_DISPLAY_NAME_MAX = 64
_MCP_STREAMABLE_HTTP_ACCEPT = "application/json, text/event-stream"

Transport = Literal["streamable_http", "stdio"]


def is_custom_mcp_kind(kind: str) -> bool:
    return kind == CUSTOM_MCP_KIND


def synthetic_instance_id(server_name: str) -> str:
    return f"custom:{server_name}"


def parse_synthetic_instance_id(instance_id: str) -> str | None:
    if not instance_id.startswith("custom:"):
        return None
    name = instance_id.removeprefix("custom:")
    return name if name else None


def server_enabled(spec: dict[str, Any]) -> bool:
    return spec.get("enabled", True) is not False


def extract_servers(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return the servers map from a decrypted credential blob."""
    if not payload:
        return {}
    raw = payload.get("servers")
    if isinstance(raw, dict):
        return dict(raw)
    # Legacy / direct map without wrapper
    if (
        raw is None
        and payload
        and "servers" not in payload
        and all(isinstance(v, dict) for v in payload.values())
    ):
        return dict(payload)
    return {}


def wrap_servers(servers: dict[str, Any]) -> dict[str, Any]:
    return {"servers": servers}


def _normalize_headers(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("headers must be an object of string keys/values")
    out: dict[str, str] = {}
    for key, value in raw.items():
        k = str(key).strip()
        if not k:
            raise ValueError("header names must be non-empty")
        out[k] = str(value)
    return out


def _normalize_env(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("env must be an object of string keys/values")
    out: dict[str, str] = {}
    for key, value in raw.items():
        k = str(key).strip()
        if not k:
            raise ValueError("env names must be non-empty")
        out[k] = str(value)
    return out


def _normalize_args(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        return lines
    if not isinstance(raw, list):
        raise ValueError("args must be a list of strings")
    return [str(item) for item in raw]


def validate_mcp_http_url(url: str) -> str:
    """Validate a user-configured MCP/connector URL.

    Local loopback deployments may use HTTP. Remote deployments must use
    public HTTPS and pass the shared SSRF guard.
    """
    text = url.strip()
    if not text:
        raise ValueError("url is required")
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("url must be http or https")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("url missing hostname")

    # Loopback HTTP/HTTPS is allowed for local MCP servers (stdio alternative).
    if host in {"localhost", "127.0.0.1", "::1"}:
        return text

    # Public remote MCP: HTTPS only + existing SSRF guards (no private IPs).
    if parsed.scheme != "https":
        raise ValueError("non-local url must use https")
    try:
        validate_https_url(text, field="url")
    except UnsafeOutboundUrl as exc:
        raise ValueError(str(exc)) from exc
    return text


def normalize_server_spec(name: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"server {name!r} must be an object")
    transport = str(raw.get("transport") or "").strip()
    if transport not in ("streamable_http", "stdio", "http"):
        raise ValueError(f"server {name!r}: transport must be streamable_http or stdio")
    if transport == "http":
        transport = "streamable_http"

    enabled = raw.get("enabled", True) is not False
    spec: dict[str, Any] = {"transport": transport, "enabled": enabled}
    if raw.get("default_open") is True:
        spec["default_open"] = True

    display_name = str(raw.get("display_name") or "").strip()
    if display_name:
        if len(display_name) > _DISPLAY_NAME_MAX:
            raise ValueError(
                f"server {name!r}: display_name must be at most {_DISPLAY_NAME_MAX} characters"
            )
        spec["display_name"] = display_name

    if transport == "streamable_http":
        url = validate_mcp_http_url(str(raw.get("url") or ""))
        spec["url"] = url
        headers = _normalize_headers(raw.get("headers"))
        if headers:
            spec["headers"] = headers
    else:
        command = str(raw.get("command") or "").strip()
        if not command:
            raise ValueError(f"server {name!r}: command is required")
        spec["command"] = command
        args = _normalize_args(raw.get("args"))
        if args:
            spec["args"] = args
        env = _normalize_env(raw.get("env"))
        if env:
            spec["env"] = env

    oauth = raw.get(_OAUTH_KEY)
    if isinstance(oauth, dict) and str(oauth.get("access_token") or "").strip():
        spec[_OAUTH_KEY] = dict(oauth)

    return spec


def server_display_name(name: str, spec: dict[str, Any] | None) -> str:
    """Friendly label for UI; falls back to the technical server key."""
    if isinstance(spec, dict):
        label = str(spec.get("display_name") or "").strip()
        if label:
            return label
    return name


def validate_servers_map(
    servers: Any,
    *,
    reserved_names: set[str] | None = None,
) -> dict[str, Any]:
    if servers is None:
        return {}
    if not isinstance(servers, dict):
        raise ValueError("servers must be an object")
    reserved = reserved_names or set()
    out: dict[str, Any] = {}
    for name, raw in servers.items():
        key = str(name).strip()
        if not key or not _SERVER_NAME_RE.match(key):
            raise ValueError(f"invalid server name {name!r}: use letters, digits, _ or -")
        if key in reserved:
            raise ValueError(f"server name {key!r} conflicts with a built-in connector")
        if key in out:
            raise ValueError(f"duplicate server name {key!r}")
        out[key] = normalize_server_spec(key, raw)
    return out


def oauth_tokens_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
    raw = spec.get(_OAUTH_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def oauth_configured(spec: dict[str, Any]) -> bool:
    oauth = oauth_tokens_from_spec(spec)
    return bool(str(oauth.get("access_token") or "").strip())


def oauth_required(spec: dict[str, Any]) -> bool:
    if oauth_configured(spec):
        return False
    oauth = oauth_tokens_from_spec(spec)
    return oauth.get("required") is True


def set_oauth_required_in_spec(spec: dict[str, Any], *, required: bool) -> dict[str, Any]:
    """Persist or clear the dashboard hint that OAuth is needed (no tokens)."""
    out = dict(spec)
    if oauth_configured(out):
        return out
    oauth = dict(oauth_tokens_from_spec(out))
    if required:
        oauth["required"] = True
        oauth.pop("access_token", None)
        oauth.pop("refresh_token", None)
        out[_OAUTH_KEY] = oauth
        return out
    oauth.pop("required", None)
    if str(oauth.get("access_token") or "").strip():
        out[_OAUTH_KEY] = oauth
    else:
        out.pop(_OAUTH_KEY, None)
    return out


def build_oauth_storage(
    tokens: dict[str, Any],
    *,
    issuer: str,
    resource: str | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "access_token": str(tokens["access_token"]),
        "oauth_issuer": issuer.rstrip("/"),
    }
    refresh = str(tokens.get("refresh_token") or "").strip()
    if refresh:
        out["refresh_token"] = refresh
    if tokens.get("expires_at") is not None:
        out["expires_at"] = int(tokens["expires_at"])
    if resource:
        out["oauth_resource"] = resource
    client_id = str(tokens.get("oauth_client_id") or "").strip()
    if client_id:
        out["oauth_client_id"] = client_id
    client_secret = tokens.get("oauth_client_secret")
    if client_secret:
        out["oauth_client_secret"] = str(client_secret)
    return out


def redact_server_for_api(spec: dict[str, Any]) -> dict[str, Any]:
    """Remove secrets; expose oauth preview for the dashboard."""
    out = {k: v for k, v in spec.items() if k != _OAUTH_KEY}
    if oauth_configured(spec):
        oauth = oauth_tokens_from_spec(spec)
        preview: dict[str, Any] = {"configured": True}
        if oauth.get("expires_at") is not None:
            preview["expires_at"] = oauth["expires_at"]
        out[_OAUTH_KEY] = preview
    elif oauth_required(spec):
        out[_OAUTH_KEY] = {"configured": False, "required": True}
    return out


def redact_servers_for_api(servers: dict[str, Any]) -> dict[str, Any]:
    return {
        name: redact_server_for_api(spec)
        for name, spec in servers.items()
        if isinstance(spec, dict)
    }


def merge_preserved_oauth(
    new_servers: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any]:
    """Drop client-supplied oauth blobs; keep stored tokens per server name."""
    out: dict[str, Any] = {}
    for name, raw in new_servers.items():
        if not isinstance(raw, dict):
            out[name] = raw
            continue
        spec = dict(raw)
        spec.pop(_OAUTH_KEY, None)
        old = existing.get(name)
        if isinstance(old, dict):
            old_oauth = old.get(_OAUTH_KEY)
            if isinstance(old_oauth, dict) and str(old_oauth.get("access_token") or "").strip():
                spec[_OAUTH_KEY] = dict(old_oauth)
            elif isinstance(old_oauth, dict) and old_oauth.get("required") is True:
                spec[_OAUTH_KEY] = {"required": True}
        out[name] = spec
    return out


def harness_spec_for_server(spec: dict[str, Any]) -> dict[str, Any]:
    """Strip Octop meta keys; keep langchain-mcp-adapters connection fields."""
    out = {k: v for k, v in spec.items() if k not in _HARNESS_STRIP_KEYS}
    # Ensure stdio always has args list for adapters.
    if out.get("transport") == "stdio" and "args" not in out:
        out["args"] = []
    # Streamable HTTP MCP requires both content types (same as built-in remote).
    if out.get("transport") == "streamable_http":
        headers = {str(k): str(v) for k, v in dict(out.get("headers") or {}).items()}
        oauth = oauth_tokens_from_spec(spec)
        token = str(oauth.get("access_token") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        headers.setdefault("Accept", _MCP_STREAMABLE_HTTP_ACCEPT)
        out["headers"] = headers
    return out


def enabled_harness_configs(servers: dict[str, Any]) -> dict[str, Any]:
    configs: dict[str, Any] = {}
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        if not server_enabled(spec):
            continue
        configs[name] = harness_spec_for_server(spec)
    return configs


def expand_custom_instances(
    *,
    parent: Any,
    servers: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build list-API dicts for each custom server (independent status)."""
    items: list[dict[str, Any]] = []
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        enabled = server_enabled(spec)
        items.append(
            {
                "instance_id": synthetic_instance_id(name),
                "kind": CUSTOM_MCP_KIND,
                "display_name": server_display_name(name, spec),
                "status": "active" if enabled else "disabled",
                "mcp_server_name": name,
                "has_credentials": True,
                "default_open": spec.get("default_open") is True,
                "created_at": parent.created_at,
                "updated_at": parent.updated_at,
            }
        )
    items.sort(key=lambda row: str(row["display_name"]).casefold())
    return items
