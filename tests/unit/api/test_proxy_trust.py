"""Reverse-proxy trust: the client address behind a rate limiter must be real.

Octop ships with every artifact bound to ``0.0.0.0`` and no proxy, and the
built-in ACME flow requires that bind — so a directly-exposed install is the
normal case, not an edge case. On that topology the client controls its own
headers, so honouring ``X-Forwarded-For`` from any peer makes the login captcha
limiter and the invite rate limiter bypassable in a few bytes. These tests pin
the default to "trust nothing" and the opt-in path to working.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from octop.api.common.proxy_trust import (
    LOOPBACK_PROXIES,
    TRUSTED_PROXIES_ENV,
    is_wildcard_bind,
    trusted_proxy_hosts,
)
from octop.api.common.public_base import resolve_public_base
from octop.api.routers.auth import _client_ip


class _Cfg:
    def __init__(self, bind_host: str, trusted: list[str] | None = None) -> None:
        self.bind_host = bind_host
        self.trusted_proxies = trusted or []


# --- the trust decision itself ------------------------------------------------


def test_wildcard_bind_trusts_nothing_by_default() -> None:
    assert trusted_proxy_hosts(_Cfg("0.0.0.0")) == []
    assert is_wildcard_bind(_Cfg("0.0.0.0")) is True


def test_loopback_bind_trusts_loopback_so_local_proxy_installs_keep_working() -> None:
    assert trusted_proxy_hosts(_Cfg("127.0.0.1")) == list(LOOPBACK_PROXIES)
    assert is_wildcard_bind(_Cfg("127.0.0.1")) is False


def test_explicit_list_wins_over_the_heuristic() -> None:
    assert trusted_proxy_hosts(_Cfg("127.0.0.1", ["10.0.0.5"])) == ["10.0.0.5"]
    # Explicit trust on a wildcard bind re-enables the old behaviour on purpose.
    assert trusted_proxy_hosts(_Cfg("0.0.0.0", ["*"])) == ["*"]


def test_missing_config_trusts_nothing() -> None:
    assert trusted_proxy_hosts(None) == []
    assert is_wildcard_bind(None) is True


def test_env_var_name_is_the_documented_one() -> None:
    assert TRUSTED_PROXIES_ENV == "OCTOP_TRUSTED_PROXIES"


# --- what the limiter actually sees -------------------------------------------


def _app(cfg: Any) -> FastAPI:
    """Mirror what uvicorn does at the server layer for this config."""
    app = FastAPI()
    hosts = trusted_proxy_hosts(cfg)
    if hosts:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=hosts)

    @app.get("/who")
    async def who(request: Request) -> dict[str, str]:
        return {
            "ip": _client_ip(request),
            "scheme": request.url.scheme,
            "origin": resolve_public_base(request),
        }

    return app


def test_spoofed_forwarded_for_cannot_change_the_rate_limit_key() -> None:
    """The headline regression: a client-supplied header must not become the key."""
    client = TestClient(_app(_Cfg("0.0.0.0")))

    resp = client.get("/who", headers={"x-forwarded-for": "1.2.3.4"})

    assert resp.json()["ip"] == "testclient", "spoofed X-Forwarded-For was honoured"


def test_trusted_proxy_sets_the_rate_limit_key() -> None:
    client = TestClient(_app(_Cfg("0.0.0.0", ["testclient"])))

    resp = client.get("/who", headers={"x-forwarded-for": "1.2.3.4"})

    assert resp.json()["ip"] == "1.2.3.4"


def test_spoofed_forwarded_proto_cannot_claim_tls() -> None:
    """`X-Forwarded-Proto` drives the SSO cookie's Secure flag — same hazard."""
    client = TestClient(_app(_Cfg("0.0.0.0")))

    resp = client.get("/who", headers={"x-forwarded-proto": "https"})

    assert resp.json()["scheme"] == "http"


def test_trusted_proxy_can_terminate_tls() -> None:
    client = TestClient(_app(_Cfg("0.0.0.0", ["testclient"])))

    resp = client.get("/who", headers={"x-forwarded-proto": "https"})

    assert resp.json()["scheme"] == "https"


def test_client_ip_ignores_the_header_even_without_middleware() -> None:
    """Belt and braces: the helper itself must never read the header."""
    from starlette.requests import Request as StarletteRequest

    scope = {
        "type": "http",
        "scheme": "http",
        "server": ("internal.example", 8080),
        "path": "/",
        "headers": [(b"host", b"internal.example"), (b"x-forwarded-for", b"9.9.9.9")],
        "client": ("10.1.2.3", 5555),
    }

    assert _client_ip(StarletteRequest(scope)) == "10.1.2.3"


@pytest.mark.parametrize("missing", [None, ""])
def test_client_ip_falls_back_when_there_is_no_peer(missing: str | None) -> None:
    from starlette.requests import Request as StarletteRequest

    scope: dict[str, Any] = {
        "type": "http",
        "scheme": "http",
        "server": ("internal.example", 8080),
        "path": "/",
        "headers": [(b"host", b"internal.example")],
    }
    if missing is not None:
        scope["client"] = (missing, 0)

    assert _client_ip(StarletteRequest(scope)) == "unknown"


def test_trusted_proxy_yields_the_public_https_origin() -> None:
    """The OIDC redirect origin behind a real proxy, which must stay correct."""
    client = TestClient(_app(_Cfg("0.0.0.0", ["testclient"])))

    resp = client.get(
        "/who",
        headers={"x-forwarded-proto": "https", "host": "octop.example"},
    )

    assert resp.json()["origin"] == "https://octop.example"


def test_untrusted_peer_cannot_claim_another_public_origin() -> None:
    client = TestClient(_app(_Cfg("0.0.0.0")))

    resp = client.get(
        "/who",
        headers={"x-forwarded-proto": "https", "x-forwarded-host": "evil.example"},
    )

    assert "evil.example" not in resp.json()["origin"]
