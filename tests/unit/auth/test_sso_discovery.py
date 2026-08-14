"""Tests for OIDC discovery helpers."""

from __future__ import annotations

import httpx
import pytest

from octop.infra.auth.sso.discovery import DiscoveryCache, fetch_discovery


def test_fetch_discovery_requests_openid_configuration() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json={"issuer": "https://issuer.example"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch_discovery("https://issuer.example/", httpx_client=client) == {
            "issuer": "https://issuer.example"
        }

    assert requested == ["https://issuer.example/.well-known/openid-configuration"]


def test_fetch_discovery_rejects_issuer_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"issuer": "https://other.example"})

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ValueError, match="does not match"),
    ):
        fetch_discovery("https://issuer.example", httpx_client=client)


def test_discovery_cache_reuses_value_until_invalidated() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"issuer": "https://issuer.example", "calls": calls})

    cache = DiscoveryCache()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert cache.get("https://issuer.example", httpx_client=client)["calls"] == 1
        assert cache.get("https://issuer.example", httpx_client=client)["calls"] == 1
        cache.invalidate("https://issuer.example")
        assert cache.get("https://issuer.example", httpx_client=client)["calls"] == 2
