"""RFC 8414 authorization-server metadata discovery for MCP issuers."""

from __future__ import annotations

import asyncio
import socket
from typing import Any

import httpx
import pytest
import pytest_asyncio

from octop.infra.connectors.oauth.discovery import discover_oauth_from_mcp_url
from octop.infra.connectors.oauth.mcp import fetch_authorization_metadata


@pytest_asyncio.fixture
async def metadata_http(monkeypatch: pytest.MonkeyPatch):
    routes: dict[str, dict[str, Any]] = {}
    requests: list[str] = []

    async def public_dns(*args: Any, **kwargs: Any):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", public_dns)

    def respond(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requests.append(url)
        if url in routes:
            return httpx.Response(200, json=routes[url])
        return httpx.Response(404)

    async def request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await client.request(method, url, **kwargs)

    monkeypatch.setattr("octop.infra.connectors.oauth.mcp.safe_request", request)
    monkeypatch.setattr("octop.infra.connectors.oauth.discovery.safe_request", request)
    return routes, requests


def authorization_metadata(issuer: str) -> dict[str, Any]:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "registration_endpoint": f"{issuer}/register",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("issuer", "metadata_url"),
    [
        (
            "https://auth.example.com",
            "https://auth.example.com/.well-known/oauth-authorization-server",
        ),
        (
            "https://auth.example.com/",
            "https://auth.example.com/.well-known/oauth-authorization-server",
        ),
        (
            "https://auth.example.com/tenant",
            "https://auth.example.com/.well-known/oauth-authorization-server/tenant",
        ),
        (
            "https://auth.example.com/tenant/",
            "https://auth.example.com/.well-known/oauth-authorization-server/tenant",
        ),
        (
            "https://auth.example.com/realms/tenant",
            "https://auth.example.com/.well-known/oauth-authorization-server/realms/tenant",
        ),
        (
            "https://auth.example.com:8443/tenant%20one",
            "https://auth.example.com:8443/.well-known/oauth-authorization-server/tenant%20one",
        ),
    ],
)
async def test_fetch_metadata_uses_rfc8414_path(issuer, metadata_url, metadata_http):
    routes, requests = metadata_http
    expected = authorization_metadata(issuer.rstrip("/"))
    routes[metadata_url] = expected

    assert await fetch_authorization_metadata(issuer) == expected
    assert requests == [metadata_url]


@pytest.mark.asyncio
async def test_mcp_discovery_with_path_scoped_issuer(metadata_http):
    routes, requests = metadata_http
    mcp_url = "https://mcp.example.com/mcp"
    issuer = "https://auth.example.com/realms/tenant"
    metadata_url = "https://auth.example.com/.well-known/oauth-authorization-server/realms/tenant"
    expected = authorization_metadata(issuer)
    routes["https://mcp.example.com/.well-known/oauth-protected-resource/mcp"] = {
        "resource": mcp_url,
        "authorization_servers": [issuer],
    }
    routes[metadata_url] = expected

    result = await discover_oauth_from_mcp_url(mcp_url, use_cache=False)

    assert result == {
        "available": True,
        "issuer": issuer,
        "resource": mcp_url,
        "metadata": expected,
        "scopes_supported": None,
        "error": None,
    }
    assert requests[-1] == metadata_url


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer", ["http://auth.example.com/tenant", "https://127.0.0.1/tenant"])
async def test_metadata_rejects_unsafe_issuer_before_fetch(issuer, metadata_http):
    _, requests = metadata_http
    with pytest.raises(ValueError):
        await fetch_authorization_metadata(issuer)
    assert requests == []


@pytest.mark.asyncio
async def test_metadata_rejects_unrelated_token_host(metadata_http):
    routes, _ = metadata_http
    issuer = "https://auth.example.com/tenant"
    metadata = authorization_metadata(issuer)
    metadata["token_endpoint"] = "https://unrelated.invalid/token"
    routes["https://auth.example.com/.well-known/oauth-authorization-server/tenant"] = metadata
    with pytest.raises(ValueError, match="host is not allowed for issuer"):
        await fetch_authorization_metadata(issuer)
