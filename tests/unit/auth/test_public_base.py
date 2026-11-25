"""Tests for public OIDC callback URL helpers."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from octop.api.common.public_base import resolve_public_base
from octop.api.common.sso_cookie import request_is_https
from octop.infra.auth.sso.public_base import build_redirect_uri


def _request(*, scheme: str = "http", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "scheme": scheme,
            "server": ("internal.example", 8080),
            "path": "/",
            "headers": headers or [(b"host", b"internal.example:8080")],
        }
    )


def test_resolve_public_base_uses_forwarded_proxy_headers() -> None:
    request = _request(
        headers=[
            (b"host", b"internal.example:8080"),
            (b"x-forwarded-proto", b"https"),
            (b"x-forwarded-host", b"octop.example"),
        ]
    )

    assert resolve_public_base(request) == "https://octop.example"


def test_resolve_public_base_uses_configured_origin_without_proxy_headers() -> None:
    request = _request(
        scheme="http",
        headers=[(b"host", b"127.0.0.1:8088")],
    )
    request.scope["app"] = type(
        "App",
        (),
        {
            "state": type(
                "State",
                (),
                {
                    "octop_server": type(
                        "Server",
                        (),
                        {
                            "config": type(
                                "Cfg", (), {"public_base_url": "https://octop.example:8674"}
                            )()
                        },
                    )()
                },
            )()
        },
    )()

    assert resolve_public_base(request) == "https://octop.example:8674"


def test_forwarded_proto_wins_over_configured_origin() -> None:
    request = _request(
        headers=[
            (b"host", b"internal.example:8080"),
            (b"x-forwarded-proto", b"https"),
            (b"x-forwarded-host", b"from-proxy.example"),
        ]
    )
    request.scope["app"] = type(
        "App",
        (),
        {
            "state": type(
                "State",
                (),
                {
                    "octop_server": type(
                        "Server",
                        (),
                        {
                            "config": type(
                                "Cfg", (), {"public_base_url": "https://configured.example"}
                            )()
                        },
                    )()
                },
            )()
        },
    )()

    assert resolve_public_base(request) == "https://from-proxy.example"


def test_resolve_public_base_uses_request_url_without_proxy_headers() -> None:
    request = _request(scheme="https", headers=[(b"host", b"octop.example")])

    assert resolve_public_base(request) == "https://octop.example"


@pytest.mark.parametrize("host", ["top:8011", "192.0.2.10:8011", "[2001:db8::1]:8011"])
def test_resolve_public_base_preserves_direct_port(host: str) -> None:
    request = _request(headers=[(b"host", host.encode())])

    assert resolve_public_base(request) == f"http://{host}"


@pytest.mark.parametrize(
    ("scheme", "host", "port", "expected"),
    [
        ("http", "top", "8011", "http://top:8011"),
        ("https", "octop.example", "8011", "https://octop.example:8011"),
        ("https", "192.0.2.10", "8443", "https://192.0.2.10:8443"),
        ("https", "[2001:db8::1]", "8443", "https://[2001:db8::1]:8443"),
        ("https", "octop.example:8011", "443", "https://octop.example:8011"),
        ("https", "[2001:db8::1]:8011", "8443", "https://[2001:db8::1]:8011"),
        ("https", "octop.example:443", "8011", "https://octop.example:443"),
        ("http", "octop.example", "80", "http://octop.example"),
        ("https", "octop.example", "443", "https://octop.example"),
        ("http", "octop.example", "443", "http://octop.example:443"),
        ("https", "octop.example", "80", "https://octop.example:80"),
        ("https", "octop.example", "1", "https://octop.example:1"),
        ("https", "octop.example", "65535", "https://octop.example:65535"),
        ("https", "octop.example", "08011", "https://octop.example:8011"),
    ],
)
def test_resolve_public_base_uses_forwarded_port(
    scheme: str, host: str, port: str, expected: str
) -> None:
    request = _request(
        headers=[
            (b"host", b"internal.example:8080"),
            (b"x-forwarded-proto", scheme.encode()),
            (b"x-forwarded-host", host.encode()),
            (b"x-forwarded-port", port.encode()),
        ]
    )

    assert resolve_public_base(request) == expected


@pytest.mark.parametrize("port", ["", "0", "65536", "-1", "+8011", "8e3", "bad", "8011/path"])
def test_resolve_public_base_ignores_invalid_forwarded_port(port: str) -> None:
    request = _request(
        headers=[
            (b"host", b"internal.example:8080"),
            (b"x-forwarded-proto", b"https"),
            (b"x-forwarded-host", b"octop.example"),
            (b"x-forwarded-port", port.encode()),
        ]
    )

    assert resolve_public_base(request) == "https://octop.example"


def test_resolve_public_base_uses_first_forwarded_values() -> None:
    request = _request(
        headers=[
            (b"host", b"internal.example:8080"),
            (b"x-forwarded-proto", b"https, http"),
            (b"x-forwarded-host", b" octop.example, internal.example "),
            (b"x-forwarded-port", b" 8011, 8080 "),
        ]
    )

    assert resolve_public_base(request) == "https://octop.example:8011"


def test_resolve_public_base_uses_forwarded_port_with_host_fallback() -> None:
    request = _request(
        headers=[
            (b"host", b"octop.example"),
            (b"x-forwarded-proto", b"https"),
            (b"x-forwarded-port", b"8011"),
        ]
    )

    assert resolve_public_base(request) == "https://octop.example:8011"


def _attach_public_base(request: Request, origin: str) -> None:
    request.scope["app"] = type(
        "App",
        (),
        {
            "state": type(
                "State",
                (),
                {
                    "octop_server": type(
                        "Server",
                        (),
                        {"config": type("Cfg", (), {"public_base_url": origin})()},
                    )()
                },
            )()
        },
    )()


def test_request_is_https_follows_configured_origin_without_proxy_headers() -> None:
    request = _request(scheme="http", headers=[(b"host", b"127.0.0.1:8088")])
    _attach_public_base(request, "https://octop.example:8674")

    assert request_is_https(request) is True


def test_request_is_https_lets_forwarded_http_win_over_configured_https() -> None:
    request = _request(
        headers=[
            (b"host", b"octop.example:8674"),
            (b"x-forwarded-proto", b"http"),
        ]
    )
    _attach_public_base(request, "https://octop.example:8674")

    assert request_is_https(request) is False


def test_request_is_https_uses_socket_scheme_when_unconfigured() -> None:
    assert request_is_https(_request(scheme="http")) is False
    assert request_is_https(_request(scheme="https")) is True


def test_build_redirect_uri_uses_oidc_callback_path() -> None:
    assert (
        build_redirect_uri("https://octop.example/")
        == "https://octop.example/api/auth/oidc/callback"
    )


def test_build_redirect_uri_accepts_oauth_callback_path() -> None:
    assert (
        build_redirect_uri("https://octop.example", "/api/auth/oauth/callback")
        == "https://octop.example/api/auth/oauth/callback"
    )
