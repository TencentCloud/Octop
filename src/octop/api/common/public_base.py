"""Resolve the externally visible HTTP origin for an incoming request."""

from __future__ import annotations

from starlette.requests import Request


def resolve_public_base(request: Request) -> str:
    """Resolve the externally visible origin for an incoming request.

    The scheme comes from ``request.url``, which ``ProxyHeadersMiddleware``
    has already rewritten from ``X-Forwarded-Proto`` when — and only when —
    a trusted reverse proxy is configured (``trusted_proxies``). An
    untrusted ``X-Forwarded-Proto`` is therefore ignored, which is what
    stops a client claiming a scheme it does not speak.

    The host is the ``Host`` header, so a reverse proxy in front of Octop
    must pass it through unchanged — the same requirement the built-in
    ACME HTTP-01 challenge already imposes.
    """
    host = request.headers.get("host") or request.url.netloc
    if not host:
        return ""
    return f"{request.url.scheme}://{host}".rstrip("/")
