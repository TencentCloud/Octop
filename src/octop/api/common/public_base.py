"""Resolve the externally visible HTTP origin for an incoming request."""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.requests import Request


def _first_header_value(value: str | None) -> str | None:
    if value is None:
        return None
    first = value.split(",", 1)[0].strip()
    return first or None


def _with_forwarded_port(host: str, scheme: str, forwarded_port: str | None) -> str:
    if not forwarded_port or not forwarded_port.isascii() or not forwarded_port.isdecimal():
        return host
    try:
        port = int(forwarded_port)
        # Keep explicit ports, including bracketed IPv6 authorities.
        if urlsplit(f"//{host}").port is not None or host.endswith(":"):
            return host
    except ValueError:
        return host
    if not 1 <= port <= 65535:
        return host
    if (scheme, port) in {("http", 80), ("https", 443)}:
        return host
    return f"{host}:{port}"


def resolve_public_base(request: Request) -> str:
    """Resolve the externally visible origin for an incoming request.

    Trusts ``X-Forwarded-Proto`` / ``X-Forwarded-Host`` when present (typical
    behind a reverse proxy). ``X-Forwarded-Port`` supplies a missing port;
    an explicit host port takes precedence. Prefer deploying Octop behind a
    trusted proxy and keeping the dashboard same-origin with the API for OIDC cookies.
    """
    forwarded_proto = _first_header_value(request.headers.get("x-forwarded-proto"))
    forwarded_host = _first_header_value(request.headers.get("x-forwarded-host"))
    if forwarded_proto:
        host = forwarded_host or request.headers.get("host")
        if host:
            forwarded_port = _first_header_value(request.headers.get("x-forwarded-port"))
            host = _with_forwarded_port(host, forwarded_proto, forwarded_port)
            return f"{forwarded_proto}://{host}".rstrip("/")

    return str(request.url.replace(path="", query="", fragment="")).rstrip("/")
