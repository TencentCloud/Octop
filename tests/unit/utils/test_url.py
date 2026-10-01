"""tests/unit/utils/test_url.py"""

from __future__ import annotations

import httpx
import pytest

from octop.infra.utils.url import format_host_for_url, normalize_nav_url


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("0.0.0.0", "0.0.0.0"),
        ("localhost", "localhost"),
        ("example.com", "example.com"),
        ("::1", "[::1]"),
        ("2001:db8::5", "[2001:db8::5]"),
        ("fe80::1%eth0", "[fe80::1%eth0]"),
        # Already bracketed (e.g. pasted from a printed URL) — do not double-wrap.
        ("[::1]", "[::1]"),
    ],
)
def test_format_host_for_url(host: str, expected: str) -> None:
    assert format_host_for_url(host) == expected


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "2001:db8::5", "localhost"])
def test_format_host_for_url_keeps_the_port_split_correct(host: str) -> None:
    """``bind_host`` reaches uvicorn verbatim and uvicorn binds any address
    containing ``:`` as ``AF_INET6``, so an IPv6 literal must keep working when it
    is put back into a URL — otherwise every client rejects it (``InvalidURL``)."""
    url = httpx.URL(f"http://{format_host_for_url(host)}:8088/api/health")
    assert url.host == host
    assert url.port == 8088


def test_empty_and_blank() -> None:
    assert normalize_nav_url("") == ""
    assert normalize_nav_url("   ") == ""


def test_bare_host_is_prefixed() -> None:
    assert normalize_nav_url("baidu.com") == "https://baidu.com"
    assert normalize_nav_url("example.com/a?q=1") == "https://example.com/a?q=1"


def test_absolute_http_urls_are_preserved() -> None:
    assert normalize_nav_url("http://x.com/") == "http://x.com/"
    assert normalize_nav_url("https://x.com/") == "https://x.com/"
    assert normalize_nav_url("HTTPS://x.com/") == "HTTPS://x.com/"


def test_protocol_relative_url_gets_https() -> None:
    """`//host` is a relative scheme URL (common when copied from a page source);
    it must not become the hostless https:////host."""
    assert normalize_nav_url("//baidu.com") == "https://baidu.com"
    assert normalize_nav_url("//example.com/path?q=1") == "https://example.com/path?q=1"


def test_non_http_scheme_with_slashes_is_rejected() -> None:
    assert normalize_nav_url("ftp://x.com") == ""
