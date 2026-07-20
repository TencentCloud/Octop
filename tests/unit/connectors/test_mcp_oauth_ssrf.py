"""Unit tests for MCP OAuth SSRF guards."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from octop.infra.connectors.oauth.mcp import (
    _ensure_mcp_oauth_url,
    _validate_metadata_endpoints,
    exchange_authorization_code,
    issuer_for_kind,
    register_dynamic_client,
)


@pytest.mark.asyncio
async def test_ensure_mcp_oauth_url_rejects_internal_token_endpoint() -> None:
    issuer = issuer_for_kind("notion")
    with pytest.raises(ValueError, match="private or reserved"):
        await _ensure_mcp_oauth_url(
            "https://127.0.0.1/oauth/token",
            issuer=issuer,
            field="token_endpoint",
        )


@pytest.mark.asyncio
async def test_ensure_mcp_oauth_url_rejects_foreign_host() -> None:
    issuer = issuer_for_kind("notion")
    with pytest.raises(ValueError, match="host is not allowed"):
        await _ensure_mcp_oauth_url(
            "https://evil.example.com/oauth/token",
            issuer=issuer,
            field="token_endpoint",
        )


@pytest.mark.asyncio
async def test_validate_metadata_endpoints_rejects_poisoned_metadata() -> None:
    issuer = issuer_for_kind("notion")
    metadata = {
        "authorization_endpoint": "https://mcp.notion.com/authorize",
        "token_endpoint": "http://169.254.169.254/",
    }
    with pytest.raises(ValueError):
        await _validate_metadata_endpoints(metadata, issuer=issuer)


@pytest.mark.asyncio
async def test_exchange_authorization_code_uses_validated_url() -> None:
    issuer = issuer_for_kind("notion")
    metadata = {
        "authorization_endpoint": "https://mcp.notion.com/authorize",
        "token_endpoint": "https://mcp.notion.com/token",
    }
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: {"access_token": "tok", "expires_in": 3600}

    with (
        patch(
            "octop.infra.connectors.oauth.mcp.safe_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_request,
        patch(
            "octop.infra.connectors.oauth.mcp._ensure_mcp_oauth_url",
            new_callable=AsyncMock,
            return_value="https://mcp.notion.com/token",
        ) as mock_validate,
    ):
        out = await exchange_authorization_code(
            metadata,
            issuer=issuer,
            client_id="cid",
            client_secret=None,
            code="code",
            redirect_uri="https://app.example/cb",
            code_verifier="verifier",
        )

    assert out["access_token"] == "tok"
    mock_validate.assert_awaited_once()
    mock_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_notion_public_http_redirect_uri_gets_actionable_error() -> None:
    issuer = issuer_for_kind("notion")
    metadata = {"registration_endpoint": "https://mcp.notion.com/register"}
    mock_resp = AsyncMock()
    mock_resp.status_code = 400
    mock_resp.json = lambda: {
        "error": "invalid_redirect_uri",
        "error_description": "Redirect URI must use HTTPS unless it is a loopback HTTP URI",
    }
    mock_resp.raise_for_status.side_effect = AssertionError("should raise clearer error first")

    with (
        patch(
            "octop.infra.connectors.oauth.mcp.safe_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ),
        patch(
            "octop.infra.connectors.oauth.mcp._ensure_mcp_oauth_url",
            new_callable=AsyncMock,
            return_value="https://mcp.notion.com/register",
        ),
        pytest.raises(ValueError, match="公网 HTTP.*Notion.*HTTPS"),
    ):
        await register_dynamic_client(
            metadata,
            issuer=issuer,
            redirect_uri="http://58.87.70.170/api/connectors/oauth/callback",
        )


@pytest.mark.asyncio
async def test_safe_request_blocks_internal_ip() -> None:
    from octop.infra.utils.ssrf_guard import UnsafeOutboundUrl, safe_request

    with pytest.raises(UnsafeOutboundUrl, match="private or reserved"):
        await safe_request("POST", "https://127.0.0.1/token", data={})
