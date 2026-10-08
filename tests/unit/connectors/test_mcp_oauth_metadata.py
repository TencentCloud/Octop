"""Bind MCP OAuth metadata to the requested authorization server (RFC 8414)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from octop.infra.connectors.oauth import discovery, mcp, registry

ISSUER = "https://auth.example.com"
MCP_URL = "https://mcp.example.com/mcp"


@pytest.fixture
def metadata() -> dict[str, Any]:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "registration_endpoint": f"{ISSUER}/register",
    }


@pytest.fixture
def requests(monkeypatch: pytest.MonkeyPatch, metadata: dict[str, Any]) -> AsyncMock:
    async def respond(method: str, url: str, **_kwargs: Any) -> httpx.Response:
        request = httpx.Request(method, url)
        if method == "POST" and url == MCP_URL:
            return httpx.Response(401, request=request)
        if "/.well-known/oauth-protected-resource" in url:
            return httpx.Response(
                200,
                json={"resource": MCP_URL, "authorization_servers": [f"{ISSUER}/"]},
                request=request,
            )
        assert method == "GET" and "/.well-known/oauth-authorization-server" in url
        return httpx.Response(200, json=metadata, request=request)

    requests = AsyncMock(side_effect=respond)
    monkeypatch.setattr(mcp, "safe_request", requests)
    monkeypatch.setattr(discovery, "safe_request", requests)
    monkeypatch.setattr(mcp, "validate_https_url_resolved", AsyncMock())
    monkeypatch.setattr(discovery, "_discovery_cache", {})
    return requests


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "issuer_fields",
    [
        pytest.param({}, id="missing"),
        pytest.param({"issuer": ""}, id="empty"),
        pytest.param({"issuer": None}, id="null"),
        pytest.param({"issuer": 123}, id="number"),
        pytest.param({"issuer": [ISSUER]}, id="array"),
        pytest.param({"issuer": {"url": ISSUER}}, id="object"),
        pytest.param({"issuer": "https://other.example.com"}, id="other-host"),
        pytest.param({"issuer": f"{ISSUER}/other-tenant"}, id="same-host-other-tenant"),
        pytest.param({"issuer": f"{ISSUER}/"}, id="response-trailing-slash"),
        pytest.param({"issuer": f" {ISSUER}"}, id="response-whitespace"),
        pytest.param({"issuer": "https://AUTH.example.com"}, id="response-host-case"),
    ],
)
async def test_rejects_metadata_before_validating_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    metadata: dict[str, Any],
    requests: AsyncMock,
    issuer_fields: dict[str, Any],
) -> None:
    metadata.pop("issuer")
    metadata.update(issuer_fields)
    validate_endpoints = AsyncMock(return_value=metadata)
    monkeypatch.setattr(mcp, "_validate_metadata_endpoints", validate_endpoints)

    with pytest.raises(ValueError, match="issuer"):
        await mcp.fetch_authorization_metadata(ISSUER)

    requests.assert_awaited_once()
    validate_endpoints.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["", "/tenant"])
@pytest.mark.parametrize("trailing_slash", ["", "/"])
async def test_accepts_exact_canonical_issuer(
    metadata: dict[str, Any], requests: AsyncMock, path: str, trailing_slash: str
) -> None:
    issuer = ISSUER + path
    metadata["issuer"] = issuer

    result = await mcp.fetch_authorization_metadata(issuer + trailing_slash)

    assert result == metadata
    requests.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("returned_issuer", [None, f"{ISSUER}/other-tenant"])
async def test_discovery_rejects_invalid_metadata_without_caching_it(
    metadata: dict[str, Any], requests: AsyncMock, returned_issuer: str | None
) -> None:
    metadata["issuer"] = returned_issuer

    rejected = await discovery.discover_oauth_from_mcp_url(MCP_URL)

    assert rejected["available"] is False
    assert rejected["issuer"] == ISSUER
    assert "issuer" in rejected["error"]
    assert "metadata" not in rejected

    metadata["issuer"] = ISSUER
    accepted = await discovery.discover_oauth_from_mcp_url(MCP_URL)

    assert accepted["available"] is True
    assert accepted["metadata"] == metadata
    assert requests.await_count == 6
    assert await discovery.discover_oauth_from_mcp_url(MCP_URL) == accepted
    assert requests.await_count == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("target_type", ["catalog", "custom_mcp"])
async def test_invalid_issuer_cannot_start_client_registration(
    monkeypatch: pytest.MonkeyPatch,
    metadata: dict[str, Any],
    requests: AsyncMock,
    target_type: str,
) -> None:
    if target_type == "catalog":
        catalog_issuer = mcp.issuer_for_kind("notion")
        metadata.update(
            {key: value.replace(ISSUER, catalog_issuer) for key, value in metadata.items()}
        )
    issuer = metadata["issuer"]
    metadata["issuer"] = f"{issuer}/other-tenant"
    register = AsyncMock(return_value={"client_id": "test-client"})
    monkeypatch.setattr(registry, "register_dynamic_client", register)

    with pytest.raises(ValueError, match="issuer"):
        await registry.start_oauth_for_target(
            target={"type": target_type, "kind": "notion", "server_name": "test-server"},
            mcp_url=MCP_URL,
            redirect_uri="https://octop.example.com/api/connectors/oauth/callback",
            state="test-state",
            settings_repo=None,
        )

    register.assert_not_awaited()
    assert requests.await_count == (1 if target_type == "catalog" else 3)
