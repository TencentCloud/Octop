"""User-defined MCP servers (streamable_http / stdio) stored as one connector doc."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal
from urllib.parse import urlparse

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.ssrf_guard import (
    UnsafeOutboundUrl,
    is_private_or_local_host,
    validate_https_url,
)

logger = logging.getLogger(__name__)

CUSTOM_MCP_KIND = "custom-mcp"
CUSTOM_MCP_DISPLAY_NAME = "自定义 MCP"

_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_META_KEYS = frozenset({"enabled", "display_name", "default_open", "shared"})
_OAUTH_KEY = "oauth"
_SECRET_KEYS = frozenset({_OAUTH_KEY})
_HARNESS_STRIP_KEYS = _META_KEYS | _SECRET_KEYS
_DISPLAY_NAME_MAX = 64
_MCP_STREAMABLE_HTTP_ACCEPT = "application/json, text/event-stream"

# --- Per-user scope placeholders -------------------------------------------------
# A ``headers`` value may reference the *requesting* user via ``${octop.user_id}``
# or ``${octop.username}``. The template is stored verbatim and substituted when
# Octop materializes the MCP connection spec for one user, so a single
# ``shared: true`` connector can carry a different identity header per end user
# (e.g. a multi-tenant server that keys sessions by a tenant header) instead of
# forcing one private connector per user.
_USER_SCOPE_TOKENS = frozenset({"user_id", "username"})
_USER_SCOPE_RE = re.compile(r"\$\{octop\.([A-Za-z_][A-Za-z0-9_]*)\}")
_USER_SCOPE_LITERAL = "${octop."
# A resolved value becomes part of an HTTP header *and* usually feeds a
# server-side identity key. Keep it inside the strictest shape those consumers
# accept: ``[A-Za-z0-9._-]`` and 64 chars. Anything looser is not cosmetic - a
# downstream app that rejects the key tends to fall back to one shared default
# identity, which silently merges every user back together.
_SCOPE_VALUE_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
_SCOPE_VALUE_MAX = 64
# Sanity bound for the raw header text before the identity budget is applied;
# overshoots drop to the numeric id instead of being truncated (truncation can
# make two users collide on the same key).
_SCOPE_VALUE_HARD_MAX = 512

Transport = Literal["streamable_http", "stdio"]


def is_custom_mcp_kind(kind: str) -> bool:
    return kind == CUSTOM_MCP_KIND


def synthetic_instance_id(server_name: str) -> str:
    return f"custom:{server_name}"


def shared_synthetic_instance_id(parent_instance_id: str, server_name: str) -> str:
    return f"custom:{parent_instance_id}:{server_name}"


def shared_mcp_server_name(parent_instance_id: str, server_name: str) -> str:
    return f"custom__{parent_instance_id}__{server_name}"


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

    Loopback and LAN (private / link-local) hosts may use HTTP or HTTPS with no
    SSRF restriction — operators deliberately point connectors at local MCP
    servers. Public remote hosts must use HTTPS and pass the shared SSRF guard
    (literal private/reserved IPs rejected).
    """
    text = url.strip()
    if not text:
        raise OctopError(
            ErrorCode.CONNECTOR_MCP_URL_INVALID,
            "url is required",
            details={"reason": "url is required"},
        )
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        raise OctopError(
            ErrorCode.CONNECTOR_MCP_URL_INVALID,
            "url must be http or https",
            details={"reason": "url must be http or https"},
        )
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise OctopError(
            ErrorCode.CONNECTOR_MCP_URL_INVALID,
            "url missing hostname",
            details={"reason": "url missing hostname"},
        )

    # Local / LAN MCP: allow http(s) without the outbound SSRF private-IP ban.
    if is_private_or_local_host(host):
        return text

    # Public remote MCP: HTTPS only + existing SSRF guards.
    if parsed.scheme != "https":
        raise OctopError(
            ErrorCode.CONNECTOR_MCP_HTTPS_REQUIRED,
            "public MCP server URLs must use https",
        )
    try:
        validate_https_url(text, field="url")
    except UnsafeOutboundUrl as exc:
        raise OctopError(
            ErrorCode.CONNECTOR_MCP_URL_INVALID,
            str(exc),
            details={"reason": str(exc)},
        ) from exc
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
    if raw.get("shared") is True:
        spec["shared"] = True

    display_name = str(raw.get("display_name") or "").strip()
    if display_name:
        if len(display_name) > _DISPLAY_NAME_MAX:
            raise ValueError(
                f"server {name!r}: display_name must be at most {_DISPLAY_NAME_MAX} characters"
            )
        spec["display_name"] = display_name

    if transport == "streamable_http":
        raw_url = str(raw.get("url") or "").strip()
        validate_url_template(name, raw_url)
        # Validate the host through a filled-in copy, but store the template as
        # configured so the dashboard keeps showing what the operator wrote.
        validate_mcp_http_url(url_template_probe(raw_url))
        spec["url"] = raw_url
        headers = _normalize_headers(raw.get("headers"))
        if headers:
            spec["headers"] = headers
        validate_user_scope_templates(name, spec)
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
    if isinstance(oauth, dict):
        if str(oauth.get("access_token") or "").strip():
            spec[_OAUTH_KEY] = dict(oauth)
        elif oauth.get("required") is True:
            spec[_OAUTH_KEY] = {"required": True}

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


def mark_oauth_reauth_required(spec: dict[str, Any]) -> dict[str, Any]:
    """Drop stale OAuth tokens and flag the dashboard to prompt re-authorization."""
    out = {k: v for k, v in spec.items() if k != _OAUTH_KEY}
    out[_OAUTH_KEY] = {"required": True}
    return out


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


def harness_spec_for_server(
    spec: dict[str, Any],
    *,
    user_scope: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Strip Octop meta keys; keep langchain-mcp-adapters connection fields.

    ``user_scope`` (see :func:`user_scope_context`) resolves ``${octop.*}``
    placeholders in the url path and header values for the user this connection
    is built for.
    """
    out = {k: v for k, v in spec.items() if k not in _HARNESS_STRIP_KEYS}
    # Ensure stdio always has args list for adapters.
    if out.get("transport") == "stdio" and "args" not in out:
        out["args"] = []
    # Streamable HTTP MCP requires both content types (same as built-in remote).
    if out.get("transport") == "streamable_http":
        if isinstance(out.get("url"), str):
            out["url"] = resolve_user_scope_url(out["url"], user_scope)
        headers = {str(k): str(v) for k, v in dict(out.get("headers") or {}).items()}
        oauth = oauth_tokens_from_spec(spec)
        token = str(oauth.get("access_token") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        headers.setdefault("Accept", _MCP_STREAMABLE_HTTP_ACCEPT)
        out["headers"] = apply_user_scope(headers, user_scope)
    return out


def sanitize_scope_value(raw: Any) -> str:
    """Keep a substituted value header-safe: ASCII, no CR/LF, bounded length."""
    text = _SCOPE_VALUE_SAFE_RE.sub("_", str(raw or "").strip())
    return text[:_SCOPE_VALUE_HARD_MAX]


def user_scope_context(*, user_id: int, username: str | None = None) -> dict[str, str]:
    """Build the ``${octop.*}`` substitution map for one end user.

    ``username`` falls back to the numeric id when it is missing, collapses to
    only dots, or cannot fit ``_SCOPE_VALUE_MAX`` - in every case the id is
    still unique, whereas a blank/oversized value would be rejected downstream
    and collapse all users onto the same server-side tenant/session (exactly
    the cross-account leak this feature is meant to prevent).
    """
    uid = sanitize_scope_value(int(user_id))
    name = sanitize_scope_value(username or "")
    if not name or not name.strip(".") or len(name) > _SCOPE_VALUE_MAX:
        name = uid
    return {"user_id": uid, "username": name}


def iter_user_scope_tokens(spec: dict[str, Any]) -> set[str]:
    """Every ``${octop.<token>}`` name referenced by a spec's url or header values."""
    found: set[str] = set()
    headers = spec.get("headers")
    if isinstance(headers, dict):
        for value in headers.values():
            found.update(match.group(1) for match in _USER_SCOPE_RE.finditer(str(value)))
    url = spec.get("url")
    if isinstance(url, str):
        found.update(match.group(1) for match in _USER_SCOPE_RE.finditer(url))
    return found


def validate_user_scope_templates(name: str, spec: dict[str, Any]) -> None:
    """Reject unknown placeholder tokens at save/probe time so typos fail loudly."""
    unknown = sorted(iter_user_scope_tokens(spec) - _USER_SCOPE_TOKENS)
    if unknown:
        supported = ", ".join(f"${{octop.{token}}}" for token in sorted(_USER_SCOPE_TOKENS))
        raise ValueError(
            f"server {name!r}: unknown placeholder(s): {', '.join(unknown)}; supported: {supported}"
        )


def validate_url_template(name: str, url: str) -> None:
    """Keep ``${octop.*}`` below the host so URL validation still sees a real host.

    Only the path/query may be templated; a templated scheme or hostname would
    move the SSRF / HTTPS decision to after the check has run.
    """
    if _USER_SCOPE_LITERAL not in url:
        return
    body = url[url.find("://") + 3 :] if "://" in url else url
    authority = body.split("/", 1)[0].split("?", 1)[0]
    if _USER_SCOPE_LITERAL in authority:
        raise ValueError(
            f"server {name!r}: placeholders are only allowed in the url path or query, not the host"
        )


def url_template_probe(url: str) -> str:
    """Return *url* with placeholders filled by a dummy segment, for validation."""
    return _USER_SCOPE_RE.sub(lambda m: "u", url)


def resolve_user_scope_url(url: str, scope: dict[str, str] | None) -> str:
    """Resolve ``${octop.*}`` in a streamable-HTTP url for one user.

    The host is never templated (see :func:`validate_url_template`), so the saved
    URL already passed host validation and re-validating the resolved text adds
    nothing.
    """
    if not scope or _USER_SCOPE_LITERAL not in url:
        return url
    resolved = _USER_SCOPE_RE.sub(lambda m: scope.get(m.group(1), m.group(0)), url)
    if _USER_SCOPE_LITERAL in resolved:
        raise ValueError(f"url {url!r} references an unknown placeholder")
    return resolved


def _render_all_tokens_as_uid(text: str, uid: str) -> str:
    """Re-render *text* with every placeholder replaced by the numeric id.

    Used when the resolved value does not fit ``_SCOPE_VALUE_MAX``: the numeric id
    is always in budget and still unique per user, and replacing every token
    wholesale avoids truncation, which could collide two long names onto one key.
    """
    return _USER_SCOPE_RE.sub(lambda _m: uid, text)


def apply_user_scope(
    headers: dict[str, str],
    scope: dict[str, str] | None,
) -> dict[str, str]:
    """Resolve ``${octop.<token>}`` in header values against *scope*.

    Without a scope the template is left untouched — callers that open a live
    connection must pass one (``ConnectorService.user_scope_for``), while API
    previews keep the literal so the configured template stays visible.

    A resolved value that no longer fits ``_SCOPE_VALUE_MAX`` is re-rendered
    with the numeric id for every token (still unique per user); a template
    whose literal text alone is too big raises, because sending it would get the
    key rejected server-side and silently merge users onto one identity.
    """
    if not scope:
        return headers
    out: dict[str, str] = {}
    for key, value in headers.items():
        text = str(value)
        if _USER_SCOPE_LITERAL not in text:
            out[key] = text
            continue
        resolved = _USER_SCOPE_RE.sub(lambda m: scope.get(m.group(1), m.group(0)), text)
        if len(resolved) > _SCOPE_VALUE_MAX:
            resolved = _render_all_tokens_as_uid(text, scope.get("user_id") or "")
            if len(resolved) > _SCOPE_VALUE_MAX:
                raise ValueError(
                    f"header {key!r}: resolved value does not fit {_SCOPE_VALUE_MAX} "
                    f"characters; shorten the literal part of the template"
                )
        out[key] = resolved
    return out


def enabled_harness_configs(
    servers: dict[str, Any],
    *,
    user_scope: dict[str, str] | None = None,
) -> dict[str, Any]:
    configs: dict[str, Any] = {}
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        if not server_enabled(spec):
            continue
        try:
            configs[name] = harness_spec_for_server(spec, user_scope=user_scope)
        except ValueError as exc:
            # A template that cannot be resolved for this user is dropped rather
            # than sent: the server would reject the key and fall back to one
            # shared identity, which is the leak this feature exists to avoid.
            logger.warning("custom MCP server %s skipped for this user: %s", name, exc)
    return configs


def expand_custom_instances(
    *,
    parent: Any,
    servers: dict[str, Any],
    shared_view: bool = False,
) -> list[dict[str, Any]]:
    """Build list-API dicts for each custom server (independent status)."""
    items: list[dict[str, Any]] = []
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        enabled = server_enabled(spec)
        if shared_view and spec.get("shared") is not True:
            continue
        items.append(
            {
                "instance_id": (
                    shared_synthetic_instance_id(parent.instance_id, name)
                    if shared_view
                    else synthetic_instance_id(name)
                ),
                "kind": CUSTOM_MCP_KIND,
                "display_name": server_display_name(name, spec),
                "status": "active" if enabled else "disabled",
                "mcp_server_name": (
                    shared_mcp_server_name(parent.instance_id, name) if shared_view else name
                ),
                "has_credentials": True,
                "default_open": spec.get("default_open") is True,
                "shared": spec.get("shared") is True,
                "owner_user_id": parent.user_id,
                "created_at": parent.created_at,
                "updated_at": parent.updated_at,
            }
        )
    items.sort(key=lambda row: str(row["display_name"]).casefold())
    return items
