"""Unit tests for TLS preflight checks."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import httpx
import pytest

from octop.config import OctopConfig, TlsConfig
from octop.infra.setup.tls import preflight as preflight_mod
from octop.infra.setup.tls.preflight import (
    _METADATA_PUBLIC_IP_URLS,
    _PUBLIC_IP_HTTPS_URLS,
    _fetch_public_ip,
    _parse_public_ipv4,
    run_preflight,
)

_PUBLIC_IP = "1.2.3.4"


def _fake_client(handler: Callable[[str], object]) -> type:
    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get(self, url: str) -> object:
            return handler(url)

    return FakeClient


class _OkResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _ErrorResponse:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def raise_for_status(self) -> None:
        raise httpx.HTTPStatusError(
            "boom",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )


def test_preflight_requires_domain():
    result = run_preflight("", OctopConfig())
    assert not result.ok
    assert any(c.id == "domain" and not c.ok for c in result.checks)


def test_preflight_bind_host_and_port(tmp_path):
    cfg = OctopConfig(bind_host="127.0.0.1", port=8088)
    with (
        patch("octop.infra.setup.tls.preflight._port_available", return_value=True),
        patch("octop.infra.setup.tls.preflight._fetch_public_ip", return_value=_PUBLIC_IP),
        patch("octop.infra.setup.tls.preflight._resolve_domain_ips", return_value={_PUBLIC_IP}),
    ):
        result = run_preflight("octop.example.com", cfg)
    assert not result.ok
    ids = {c.id for c in result.checks}
    assert "bind_host" in ids
    assert "port" in ids
    bind = next(c for c in result.checks if c.id == "bind_host")
    port = next(c for c in result.checks if c.id == "port")
    assert not bind.ok
    assert not port.ok


def test_preflight_ok_when_all_match():
    cfg = OctopConfig(
        bind_host="0.0.0.0",
        port=80,
        tls=TlsConfig(enabled=False),
    )
    with (
        patch("octop.infra.setup.tls.preflight._port_available", return_value=True),
        patch("octop.infra.setup.tls.preflight._fetch_public_ip", return_value=_PUBLIC_IP),
        patch("octop.infra.setup.tls.preflight._resolve_domain_ips", return_value={_PUBLIC_IP}),
    ):
        result = run_preflight("octop.example.com", cfg)
    assert result.ok
    assert all(c.ok for c in result.checks)


def test_preflight_rejects_when_tls_already_enabled():
    cfg = OctopConfig(
        bind_host="0.0.0.0",
        port=8088,
        tls=TlsConfig(enabled=True),
    )
    with (
        patch("octop.infra.setup.tls.preflight._port_available", return_value=True),
        patch("octop.infra.setup.tls.preflight._fetch_public_ip", return_value=_PUBLIC_IP),
        patch("octop.infra.setup.tls.preflight._resolve_domain_ips", return_value={_PUBLIC_IP}),
    ):
        result = run_preflight("octop.example.com", cfg)
    assert not result.ok
    assert any(c.id == "tls_enabled" and not c.ok for c in result.checks)


def test_preflight_renewal_mode_dual_port():
    cfg = OctopConfig(
        bind_host="0.0.0.0",
        port=443,
        tls=TlsConfig(enabled=True, http_port=80),
    )
    with (
        patch("octop.infra.setup.tls.preflight._fetch_public_ip", return_value=_PUBLIC_IP),
        patch("octop.infra.setup.tls.preflight._resolve_domain_ips", return_value={_PUBLIC_IP}),
    ):
        result = run_preflight("octop.example.com", cfg)
    assert result.renewal
    assert result.ok
    assert any(c.id == "dual_port" and c.ok for c in result.checks)


def test_preflight_fails_when_public_ip_unavailable():
    cfg = OctopConfig(
        bind_host="0.0.0.0",
        port=80,
        tls=TlsConfig(enabled=False),
    )
    with (
        patch("octop.infra.setup.tls.preflight._port_available", return_value=True),
        patch("octop.infra.setup.tls.preflight._fetch_public_ip", return_value=None),
        patch("octop.infra.setup.tls.preflight._resolve_domain_ips", return_value={_PUBLIC_IP}),
    ):
        result = run_preflight("octop.example.com", cfg, locale="zh")
    assert not result.ok
    check = next(c for c in result.checks if c.id == "public_ip")
    assert not check.ok
    assert "公网 IP" in check.message


def test_preflight_dns_mismatch():
    cfg = OctopConfig(
        bind_host="0.0.0.0",
        port=80,
        tls=TlsConfig(enabled=False),
    )
    with (
        patch("octop.infra.setup.tls.preflight._port_available", return_value=True),
        patch("octop.infra.setup.tls.preflight._fetch_public_ip", return_value=_PUBLIC_IP),
        patch(
            "octop.infra.setup.tls.preflight._resolve_domain_ips",
            return_value={"9.9.9.9"},
        ),
    ):
        result = run_preflight("octop.example.com", cfg, locale="zh")
    assert not result.ok
    check = next(c for c in result.checks if c.id == "dns")
    assert not check.ok
    assert _PUBLIC_IP in check.message
    assert "9.9.9.9" in check.message


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.2.3.4", "1.2.3.4"),
        ("当前 IP：1.2.3.4 来自于 测试\n", "1.2.3.4"),
        ("10.0.0.1", None),
        ("127.0.0.1", None),
        ("169.254.169.254", None),
        ("not an ip", None),
        ("", None),
    ],
)
def test_parse_public_ipv4(text: str, expected: str | None) -> None:
    assert _parse_public_ipv4(text) == expected


def test_default_probe_url_lists_prefer_cn_and_cloud() -> None:
    assert urlparse(_METADATA_PUBLIC_IP_URLS[0]).hostname == "metadata.tencentyun.com"
    assert any(urlparse(url).hostname == "100.100.100.200" for url in _METADATA_PUBLIC_IP_URLS)
    assert urlparse(_PUBLIC_IP_HTTPS_URLS[0]).hostname == "4.ipw.cn"
    assert "https://api.ipify.org?format=text" in _PUBLIC_IP_HTTPS_URLS
    assert _PUBLIC_IP_HTTPS_URLS.index("https://4.ipw.cn/") < _PUBLIC_IP_HTTPS_URLS.index(
        "https://api.ipify.org?format=text"
    )


def test_fetch_public_ip_falls_back_past_unreachable_endpoints() -> None:
    calls: list[str] = []

    def handler(url: str) -> object:
        calls.append(url)
        host = urlparse(url).hostname or ""
        if host == "api.ipify.org":
            raise httpx.ConnectError("blocked")
        if host == "4.ipw.cn":
            return _OkResponse(_PUBLIC_IP)
        raise httpx.ConnectError("skip")

    with (
        patch.object(preflight_mod, "_METADATA_PUBLIC_IP_URLS", ()),
        patch.object(
            preflight_mod,
            "_PUBLIC_IP_HTTPS_URLS",
            (
                "https://api.ipify.org?format=text",
                "https://4.ipw.cn/",
            ),
        ),
        patch("octop.infra.setup.tls.preflight.httpx.Client", _fake_client(handler)),
    ):
        assert _fetch_public_ip() == _PUBLIC_IP
    assert calls == [
        "https://api.ipify.org?format=text",
        "https://4.ipw.cn/",
    ]


def test_fetch_public_ip_skips_non_public_bodies() -> None:
    calls: list[str] = []

    def handler(url: str) -> object:
        calls.append(url)
        if url.endswith("/empty"):
            return _OkResponse("")
        if url.endswith("/private"):
            return _OkResponse("10.0.0.1")
        if url.endswith("/html"):
            return _OkResponse("<html>no ip here</html>")
        if url.endswith("/ok"):
            return _OkResponse(_PUBLIC_IP)
        raise httpx.ConnectError("unexpected")

    with (
        patch.object(preflight_mod, "_METADATA_PUBLIC_IP_URLS", ()),
        patch.object(
            preflight_mod,
            "_PUBLIC_IP_HTTPS_URLS",
            (
                "https://example.test/empty",
                "https://example.test/private",
                "https://example.test/html",
                "https://example.test/ok",
            ),
        ),
        patch("octop.infra.setup.tls.preflight.httpx.Client", _fake_client(handler)),
    ):
        assert _fetch_public_ip() == _PUBLIC_IP
    assert calls == [
        "https://example.test/empty",
        "https://example.test/private",
        "https://example.test/html",
        "https://example.test/ok",
    ]


def test_fetch_public_ip_prefers_cloud_metadata() -> None:
    def handler(url: str) -> object:
        assert urlparse(url).hostname == "metadata.tencentyun.com"
        return _OkResponse(_PUBLIC_IP)

    with (
        patch.object(
            preflight_mod,
            "_METADATA_PUBLIC_IP_URLS",
            ("http://metadata.tencentyun.com/latest/meta-data/public-ipv4",),
        ),
        patch.object(preflight_mod, "_PUBLIC_IP_HTTPS_URLS", ("https://should-not-call/",)),
        patch("octop.infra.setup.tls.preflight.httpx.Client", _fake_client(handler)),
    ):
        assert _fetch_public_ip() == _PUBLIC_IP


def test_fetch_public_ip_falls_through_metadata_to_https() -> None:
    calls: list[str] = []

    def handler(url: str) -> object:
        calls.append(url)
        host = urlparse(url).hostname or ""
        if host in {"metadata.tencentyun.com", "100.100.100.200"}:
            raise httpx.ConnectError("not on cloud")
        if host == "4.ipw.cn":
            return _OkResponse(_PUBLIC_IP)
        raise httpx.ConnectError("skip")

    with (
        patch.object(
            preflight_mod,
            "_METADATA_PUBLIC_IP_URLS",
            ("http://metadata.tencentyun.com/latest/meta-data/public-ipv4",),
        ),
        patch.object(
            preflight_mod,
            "_PUBLIC_IP_HTTPS_URLS",
            ("https://4.ipw.cn/",),
        ),
        patch("octop.infra.setup.tls.preflight.httpx.Client", _fake_client(handler)),
    ):
        assert _fetch_public_ip() == _PUBLIC_IP
    assert calls == [
        "http://metadata.tencentyun.com/latest/meta-data/public-ipv4",
        "https://4.ipw.cn/",
    ]


def test_fetch_public_ip_returns_none_when_all_sources_fail() -> None:
    def handler(url: str) -> object:
        if url.endswith("/http-error"):
            return _ErrorResponse()
        raise httpx.ConnectError("down")

    with (
        patch.object(
            preflight_mod,
            "_METADATA_PUBLIC_IP_URLS",
            ("http://metadata.example/missing",),
        ),
        patch.object(
            preflight_mod,
            "_PUBLIC_IP_HTTPS_URLS",
            (
                "https://example.test/http-error",
                "https://example.test/connect-error",
            ),
        ),
        patch("octop.infra.setup.tls.preflight.httpx.Client", _fake_client(handler)),
    ):
        assert _fetch_public_ip() is None
