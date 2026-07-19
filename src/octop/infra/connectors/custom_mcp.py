"""User-defined MCP servers (streamable_http / stdio) stored as one connector doc."""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

from octop.infra.utils.ssrf_guard import UnsafeOutboundUrl, validate_https_url

CUSTOM_MCP_KIND = "custom-mcp"
CUSTOM_MCP_DISPLAY_NAME = "自定义 MCP"

_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_META_KEYS = frozenset({"enabled"})
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


def _validate_http_url(url: str) -> str:
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

    if transport == "streamable_http":
        url = _validate_http_url(str(raw.get("url") or ""))
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

    return spec


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


def harness_spec_for_server(spec: dict[str, Any]) -> dict[str, Any]:
    """Strip Octop meta keys; keep langchain-mcp-adapters connection fields."""
    out = {k: v for k, v in spec.items() if k not in _META_KEYS}
    # Ensure stdio always has args list for adapters.
    if out.get("transport") == "stdio" and "args" not in out:
        out["args"] = []
    # Streamable HTTP MCP requires both content types (same as built-in remote).
    if out.get("transport") == "streamable_http":
        headers = {str(k): str(v) for k, v in dict(out.get("headers") or {}).items()}
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
                "display_name": name,
                "status": "active" if enabled else "disabled",
                "mcp_server_name": name,
                "has_credentials": True,
                "created_at": parent.created_at,
                "updated_at": parent.updated_at,
            }
        )
    items.sort(key=lambda row: str(row["display_name"]))
    return items
