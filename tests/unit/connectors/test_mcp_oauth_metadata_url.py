"""RFC 8414 metadata URLs for root and path-scoped MCP OAuth issuers."""

from __future__ import annotations

import asyncio
import socket
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from octop.infra.connectors.oauth import discovery, mcp

_AUTHORITY = "https://auth.example.com"
_WELL_KNOWN = "/.well-known/oauth-authorization-server"


def _metadata(issuer: str) -> dict[str, Any]:
    issuer = issuer.rstrip("/")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "registration_endpoint": f"{issuer}/register",
        "scopes_supported": ["mcp:tools"],
    }


@pytest.fixture
async def public_dns(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    resolver = AsyncMock(
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443))
        ]
    )
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolver)
    return resolver


@pytest.mark.parametrize("port", ["", ":8443"])
@pytest.mark.parametrize(
    ("issuer_path", "metadata_path"),
    [
        ("", _WELL_KNOWN),
        ("/", _WELL_KNOWN),
        ("/realms/tenant", f"{_WELL_KNOWN}/realms/tenant"),
        ("/realms/tenant/", f"{_WELL_KNOWN}/realms/tenant"),
        ("/realms/team%2Ftenant", f"{_WELL_KNOWN}/realms/team%2Ftenant"),
        ("/realms/tenant%20name%3Bv1/", f"{_WELL_KNOWN}/realms/tenant%20name%3Bv1"),
    ],
)
async def test_fetches_metadata_from_rfc8414_url(
    monkeypatch: pytest.MonkeyPatch,
    public_dns: AsyncMock,
    port: str,
    issuer_path: str,
    metadata_path: str,
) -> None:
    issuer = f"{_AUTHORITY}{port}{issuer_path}"
    metadata = _metadata(issuer)
    expected_url = f"{_AUTHORITY}{port}{metadata_path}"

    async def respond(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        return httpx.Response(
            200 if url == expected_url else 404,
            json=metadata,
            request=httpx.Request(method, url),
        )

    request = AsyncMock(side_effect=respond)
    monkeypatch.setattr(mcp, "safe_request", request)

    assert await mcp.fetch_authorization_metadata(issuer) == metadata
    request.assert_awaited_once_with("GET", expected_url, timeout=20.0)
    assert public_dns.await_args_list[0].args == ("auth.example.com", 8443 if port else 443)


@pytest.mark.parametrize("matching_issuer", [True, False])
async def test_path_scoped_discovery_uses_correct_url_and_checks_response_issuer(
    monkeypatch: pytest.MonkeyPatch, public_dns: AsyncMock, matching_issuer: bool
) -> None:
    mcp_url = "https://mcp.example.com/mcp"
    prm_url = "https://mcp.example.com/.well-known/oauth-protected-resource/mcp"
    issuer = f"{_AUTHORITY}:8443/realms/tenant%2Fone"
    metadata_url = f"{_AUTHORITY}:8443{_WELL_KNOWN}/realms/tenant%2Fone"
    metadata = _metadata(issuer)
    if not matching_issuer:
        metadata["issuer"] = f"{_AUTHORITY}:8443/realms/other"

    async def respond(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        request = httpx.Request(method, url)
        if method == "POST" and url == mcp_url:
            return httpx.Response(401, request=request)
        if method == "GET" and url == prm_url:
            return httpx.Response(
                200,
                json={"resource": mcp_url, "authorization_servers": [f"{issuer}/"]},
                request=request,
            )
        return httpx.Response(200 if url == metadata_url else 404, json=metadata, request=request)

    request = AsyncMock(side_effect=respond)
    monkeypatch.setattr(mcp, "safe_request", request)
    monkeypatch.setattr(discovery, "safe_request", request)

    result = await discovery.discover_oauth_from_mcp_url(mcp_url, use_cache=False)

    assert result["issuer"] == issuer
    assert result["available"] is matching_issuer
    if matching_issuer:
        assert result["metadata"] == metadata
        assert result["resource"] == mcp_url
        assert result["scopes_supported"] == ["mcp:tools"]
    else:
        assert "issuer" in result["error"]
        assert "metadata" not in result
    assert [(call.args[0], call.args[1]) for call in request.await_args_list] == [
        ("POST", mcp_url),
        ("GET", prm_url),
        ("GET", metadata_url),
    ]
    assert public_dns.await_count > 0


@pytest.mark.parametrize(
    "issuer",
    [
        "http://auth.example.com/realms/tenant",
        "https://localhost/realms/tenant",
        "https://127.0.0.1/realms/tenant",
    ],
)
async def test_path_scoped_metadata_keeps_https_and_host_checks(
    monkeypatch: pytest.MonkeyPatch, public_dns: AsyncMock, issuer: str
) -> None:
    request = AsyncMock()
    monkeypatch.setattr(mcp, "safe_request", request)

    with pytest.raises(ValueError):
        await mcp.fetch_authorization_metadata(issuer)

    request.assert_not_awaited()
    public_dns.assert_not_awaited()


async def test_path_scoped_metadata_rejects_private_dns_before_request(
    monkeypatch: pytest.MonkeyPatch, public_dns: AsyncMock
) -> None:
    public_dns.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443))
    ]
    request = AsyncMock()
    monkeypatch.setattr(mcp, "safe_request", request)

    with pytest.raises(ValueError, match="private or reserved"):
        await mcp.fetch_authorization_metadata(f"{_AUTHORITY}/realms/tenant")

    public_dns.assert_awaited_once()
    request.assert_not_awaited()


async def test_path_scoped_metadata_keeps_endpoint_host_checks(
    monkeypatch: pytest.MonkeyPatch, public_dns: AsyncMock
) -> None:
    issuer = f"{_AUTHORITY}/realms/tenant"
    metadata = _metadata(issuer)
    metadata["token_endpoint"] = "https://other.example.org/token"
    request = AsyncMock(
        return_value=httpx.Response(
            200,
            json=metadata,
            request=httpx.Request("GET", f"{_AUTHORITY}{_WELL_KNOWN}/realms/tenant"),
        )
    )
    monkeypatch.setattr(mcp, "safe_request", request)

    with pytest.raises(ValueError, match="host is not allowed"):
        await mcp.fetch_authorization_metadata(issuer)

    request.assert_awaited_once()
    assert public_dns.await_count == 2
