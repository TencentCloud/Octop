"""Authorization metadata must belong to the requested OAuth issuer."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from octop.infra.connectors.oauth import mcp
from octop.infra.connectors.oauth.discovery import discover_oauth_from_mcp_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "returned_issuer",
    [None, "", 123, "https://other.example.com", "https://auth.example.com/other-tenant"],
)
async def test_reject_wrong_metadata_issuer_before_using_endpoints(monkeypatch, returned_issuer):
    issuer = "https://auth.example.com"
    metadata: dict[str, Any] = {
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
    }
    if returned_issuer is not None:
        metadata["issuer"] = returned_issuer
    response = httpx.Response(200, json=metadata, request=httpx.Request("GET", issuer))
    monkeypatch.setattr(mcp, "_ensure_mcp_oauth_url", AsyncMock())
    monkeypatch.setattr(mcp, "safe_request", AsyncMock(return_value=response))
    validate_endpoints = AsyncMock(return_value=metadata)
    monkeypatch.setattr(mcp, "_validate_metadata_endpoints", validate_endpoints)

    with pytest.raises(ValueError, match="issuer"):
        await mcp.fetch_authorization_metadata(issuer)
    validate_endpoints.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer", ["https://auth.example.com", "https://auth.example.com/"])
async def test_accept_matching_canonical_issuer(monkeypatch, issuer):
    canonical = issuer.rstrip("/")
    metadata = {
        "issuer": canonical,
        "authorization_endpoint": f"{canonical}/authorize",
        "token_endpoint": f"{canonical}/token",
    }
    response = httpx.Response(200, json=metadata, request=httpx.Request("GET", issuer))
    monkeypatch.setattr(mcp, "_ensure_mcp_oauth_url", AsyncMock())
    monkeypatch.setattr(mcp, "safe_request", AsyncMock(return_value=response))
    validate_endpoints = AsyncMock(return_value=metadata)
    monkeypatch.setattr(mcp, "_validate_metadata_endpoints", validate_endpoints)

    assert await mcp.fetch_authorization_metadata(issuer) == metadata
    validate_endpoints.assert_awaited_once_with(metadata, issuer=issuer)


@pytest.mark.asyncio
async def test_discovery_does_not_advertise_mismatched_authorization_server(monkeypatch):
    from octop.infra.connectors.oauth import discovery

    issuer = "https://auth.example.com"
    resource = "https://mcp.example.com/mcp"
    metadata = {
        "issuer": "https://auth.example.com/other-tenant",
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "registration_endpoint": f"{issuer}/register",
    }
    response = httpx.Response(200, json=metadata, request=httpx.Request("GET", issuer))
    monkeypatch.setattr(mcp, "_ensure_mcp_oauth_url", AsyncMock())
    monkeypatch.setattr(mcp, "safe_request", AsyncMock(return_value=response))
    monkeypatch.setattr(discovery, "_probe_401_resource_metadata", AsyncMock(return_value=None))
    monkeypatch.setattr(
        discovery,
        "_fetch_prm_document",
        AsyncMock(return_value={"authorization_servers": [issuer], "resource": resource}),
    )

    result = await discover_oauth_from_mcp_url(resource, use_cache=False)
    assert result["available"] is False
    assert "issuer" in result["error"]
    assert result["issuer"] == issuer
    assert result["resource"] == resource
