"""``safe_request`` rebuilds the outbound URL; the rebuild must stay valid."""

from __future__ import annotations

import asyncio
import ipaddress
from typing import Any

import httpx

from octop.infra.utils import ssrf_guard

# A public anycast resolver, written the way a self-hosted IPv6 IdP would be.
_IPV6_HOST = "2606:4700:4700::1111"


class _Captured:
    def __init__(self) -> None:
        self.transport_args: list[tuple[str, str]] = []
        self.urls: list[str] = []


def _install(monkeypatch: Any, captured: _Captured, pin_ip: str) -> None:
    async def _fake_resolve(url: str) -> str:
        return pin_ip

    class _FakeTransport(httpx.AsyncBaseTransport):
        def __init__(self, target_host: str, ip: str) -> None:
            captured.transport_args.append((target_host, ip))

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            captured.urls.append(str(request.url))
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(ssrf_guard, "_resolve_validated_ip", _fake_resolve)
    monkeypatch.setattr(ssrf_guard, "PinnedIPTransport", _FakeTransport)


def test_ipv6_literal_is_a_supported_target() -> None:
    """Guard the premise: validation accepts a public IPv6 literal."""
    assert not ipaddress.ip_address(_IPV6_HOST).is_private
    assert ssrf_guard.validate_https_url(f"https://[{_IPV6_HOST}]/token")


def test_hostname_with_port_is_rebuilt_unchanged(monkeypatch: Any) -> None:
    captured = _Captured()
    _install(monkeypatch, captured, "203.0.113.7")
    asyncio.run(
        ssrf_guard.safe_request(
            "POST",
            "https://idp.example.com:8443/token",
            data={"a": "b"},
        ),
    )
    assert captured.urls == ["https://idp.example.com:8443/token"]
    assert captured.transport_args == [("idp.example.com", "203.0.113.7")]


def test_ipv6_literal_target_keeps_its_url_brackets(monkeypatch: Any) -> None:
    """``urlparse().hostname`` drops the brackets an IPv6 literal needs in a URL."""
    captured = _Captured()
    _install(monkeypatch, captured, _IPV6_HOST)
    asyncio.run(ssrf_guard.safe_request("POST", f"https://[{_IPV6_HOST}]/token"))
    # Without the brackets httpx rejects the URL as `InvalidURL: Invalid port`.
    assert captured.urls == [f"https://[{_IPV6_HOST}]/token"]
    # The pin still has to match the bare address httpx hands to the backend.
    assert captured.transport_args == [(_IPV6_HOST, _IPV6_HOST)]


def test_path_parameter_survives_the_rebuild(monkeypatch: Any) -> None:
    captured = _Captured()
    _install(monkeypatch, captured, "203.0.113.7")
    asyncio.run(
        ssrf_guard.safe_request("GET", "https://idp.example.com/mcp;session=abc?x=2"),
    )
    assert captured.urls == ["https://idp.example.com/mcp;session=abc?x=2"]
