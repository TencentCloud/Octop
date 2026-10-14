"""httpx NO_PROXY CIDR matching (issue #1347) — Linux / macOS / Windows."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from octop.infra.utils.httpx_proxy import (
    cidr_network_from_host,
    cidr_network_from_mount_pattern,
    get_environment_proxies,
    install_httpx_cidr_no_proxy,
    no_proxy_mount_key,
    split_no_proxy_hosts,
)


@pytest.fixture(autouse=True)
def _ensure_patch() -> None:
    install_httpx_cidr_no_proxy()


@pytest.fixture
def proxy_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    """Control urllib/httpx proxy lookup without touching the real environment."""
    info = {
        "http": "http://127.0.0.1:8888",
        "https": "http://127.0.0.1:8888",
        "no": "192.168.0.0/16",
    }

    def fake_getproxies() -> dict[str, str]:
        return dict(info)

    monkeypatch.setattr("urllib.request.getproxies", fake_getproxies)
    monkeypatch.setattr("httpx._utils.getproxies", fake_getproxies)
    yield info


def test_split_no_proxy_hosts_comma_and_semicolon() -> None:
    assert split_no_proxy_hosts("192.168.0.0/16, localhost") == [
        "192.168.0.0/16",
        "localhost",
    ]
    # Windows env / Internet Settings ProxyOverride uses ';'.
    assert split_no_proxy_hosts("192.168.0.0/16;10.0.0.0/8") == [
        "192.168.0.0/16",
        "10.0.0.0/8",
    ]
    assert split_no_proxy_hosts('"192.168.0.0/16"') == ["192.168.0.0/16"]
    assert split_no_proxy_hosts("") == []


def test_cidr_network_from_host_ipv4_and_ipv6() -> None:
    v4 = cidr_network_from_host("192.168.0.0/16")
    assert v4 is not None
    assert str(v4) == "192.168.0.0/16"
    assert cidr_network_from_host("192.168.103.101") is None
    v6 = cidr_network_from_host("2001:db8::/32")
    assert v6 is not None
    assert cidr_network_from_host("[2001:db8::]/32") is not None
    assert cidr_network_from_host("example.com") is None


def test_ipv6_cidr_mount_key_is_parseable_url() -> None:
    key = no_proxy_mount_key("2001:db8::/32")
    assert key == "all://[2001:db8::]/32"
    # Upstream httpx emits all://[2001:db8::/32] which raises InvalidURL.
    parsed = httpx.URL(key)
    assert parsed.host == "2001:db8::"
    assert cidr_network_from_mount_pattern(key) is not None


def _is_direct(client: httpx.Client, url: str) -> bool:
    return client._transport_for_url(httpx.URL(url)) is client._transport


def test_cidr_bypasses_proxy_for_hosts_in_range(proxy_env: dict[str, str]) -> None:
    with httpx.Client() as client:
        assert _is_direct(client, "http://192.168.103.101/v1/models")
        assert _is_direct(client, "https://192.168.1.1/health")
        assert not _is_direct(client, "http://10.0.0.1/v1")
        assert not _is_direct(client, "http://example.com/")


def test_exact_ip_and_domain_no_proxy_still_work(proxy_env: dict[str, str]) -> None:
    proxy_env["no"] = "192.168.103.101,example.com,localhost"
    with httpx.Client() as client:
        assert _is_direct(client, "http://192.168.103.101/")
        assert _is_direct(client, "http://www.example.com/")
        assert _is_direct(client, "http://localhost/")
        assert not _is_direct(client, "http://192.168.1.1/")


def test_windows_semicolon_no_proxy(proxy_env: dict[str, str]) -> None:
    proxy_env["no"] = "192.168.0.0/16;10.0.0.0/8,localhost"
    mounts = get_environment_proxies()
    assert mounts.get("all://192.168.0.0/16") is None
    assert mounts.get("all://10.0.0.0/8") is None
    assert mounts.get("all://localhost") is None
    with httpx.Client() as client:
        assert _is_direct(client, "http://192.168.103.101/")
        assert _is_direct(client, "http://10.1.2.3/")
        assert not _is_direct(client, "http://172.16.0.1/")


def test_ipv6_cidr_does_not_crash_client(proxy_env: dict[str, str]) -> None:
    proxy_env["no"] = "2001:db8::/32,::1"
    with httpx.Client() as client:
        assert _is_direct(client, "http://[2001:db8::1]/")
        assert _is_direct(client, "http://[::1]/")
        assert not _is_direct(client, "http://[2001:db9::1]/")


def test_urlpattern_cidr_match_does_not_use_network_address_only() -> None:
    from httpx._utils import URLPattern

    pattern = URLPattern("all://192.168.0.0/16")
    assert pattern.matches(httpx.URL("http://192.168.103.101/foo"))
    assert pattern.matches(httpx.URL("https://192.168.0.0/foo"))
    assert not pattern.matches(httpx.URL("http://10.0.0.1/foo"))
    assert not pattern.matches(httpx.URL("http://example.com/foo"))


def test_loopback_bypasses_system_proxy_without_no_proxy(
    proxy_env: dict[str, str],
) -> None:
    """macOS/Windows system proxies often omit a NO_PROXY / exception list."""
    proxy_env.pop("no", None)
    with httpx.Client() as client:
        assert _is_direct(client, "http://127.0.0.1/health")
        assert _is_direct(client, "http://localhost/health")
        assert _is_direct(client, "http://[::1]/health")
        assert not _is_direct(client, "http://example.com/")


def test_install_is_idempotent() -> None:
    install_httpx_cidr_no_proxy()
    install_httpx_cidr_no_proxy()
    from httpx._utils import URLPattern

    assert URLPattern("all://10.0.0.0/8").matches(httpx.URL("http://10.1.2.3/"))
