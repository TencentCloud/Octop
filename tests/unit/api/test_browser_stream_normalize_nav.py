"""tests/unit/api/test_browser_stream_normalize_nav.py"""

from __future__ import annotations

from octop.api.routers.browser.stream import _normalize_nav_url


def test_empty_and_blank() -> None:
    assert _normalize_nav_url("") == ""
    assert _normalize_nav_url("   ") == ""


def test_bare_host_is_prefixed() -> None:
    assert _normalize_nav_url("baidu.com") == "https://baidu.com"
    assert _normalize_nav_url("example.com/path?q=1") == "https://example.com/path?q=1"


def test_http_schemes_are_preserved() -> None:
    assert _normalize_nav_url("http://x.com/") == "http://x.com/"
    assert _normalize_nav_url("https://x.com/") == "https://x.com/"


def test_uppercase_scheme_is_not_double_prefixed() -> None:
    """A user-typed HTTPS:// URL must not become https://HTTPS://..."""
    assert _normalize_nav_url("HTTPS://x.com/") == "HTTPS://x.com/"
    assert _normalize_nav_url("HTTP://x.com/") == "HTTP://x.com/"
