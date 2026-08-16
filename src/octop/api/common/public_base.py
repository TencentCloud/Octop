"""Resolve the externally visible HTTP origin for an incoming request."""

from __future__ import annotations

from starlette.requests import Request


def _first_header_value(value: str | None) -> str | None:
    if value is None:
        return None
    first = value.split(",", 1)[0].strip()
    return first or None


def resolve_public_base(request: Request) -> str:
    """Resolve the externally visible origin for an incoming request.

    Trusts ``X-Forwarded-Proto`` / ``X-Forwarded-Host`` when present (typical
    behind a reverse proxy). Prefer deploying Octop behind a trusted proxy and
    keeping the dashboard same-origin with the API for OIDC cookies.
    """
    forwarded_proto = _first_header_value(request.headers.get("x-forwarded-proto"))
    forwarded_host = _first_header_value(request.headers.get("x-forwarded-host"))
    if forwarded_proto:
        host = forwarded_host or request.headers.get("host")
        if host:
            return f"{forwarded_proto}://{host}".rstrip("/")

    return str(request.url.replace(path="", query="", fragment="")).rstrip("/")
