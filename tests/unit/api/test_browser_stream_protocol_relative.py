"""tests/unit/api/test_browser_stream_protocol_relative.py"""

from __future__ import annotations

from octop.api.routers.browser.stream import _normalize_nav_url


def test_protocol_relative_url_is_not_hostless() -> None:
    assert _normalize_nav_url("//baidu.com") == "https://baidu.com"
    assert _normalize_nav_url("//example.com/path?q=1") == "https://example.com/path?q=1"


def test_existing_behaviour_is_unchanged() -> None:
    assert _normalize_nav_url("") == ""
    assert _normalize_nav_url("baidu.com") == "https://baidu.com"
    assert _normalize_nav_url("https://x.com/") == "https://x.com/"
