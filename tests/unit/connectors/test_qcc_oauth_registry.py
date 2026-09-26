"""QCC catalog integration with the shared MCP OAuth and probe flows."""

from __future__ import annotations

import hashlib
from base64 import urlsafe_b64encode
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest

from octop.infra.connectors.oauth import registry

ISSUER = "https://agent.qcc.com"
RESOURCE = f"{ISSUER}/mcp/company/stream"


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata_scopes", [None, ["mcp:tools"]])
@pytest.mark.parametrize(
    "base_url", ["http://127.0.0.1:8088", "http://localhost:8088", "https://octop.example.com"]
)
async def test_qcc_catalog_authorization_parameters(
    monkeypatch: pytest.MonkeyPatch, metadata_scopes: list[str] | None, base_url: str
) -> None:
    metadata = {
        "authorization_endpoint": f"{ISSUER}/oauth/authorize",
        "token_endpoint": f"{ISSUER}/oauth/token",
        "registration_endpoint": f"{ISSUER}/oauth/register",
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": metadata_scopes,
    }
    fetch = AsyncMock(return_value=metadata)
    register = AsyncMock(return_value={"client_id": "test-public-client"})
    monkeypatch.setattr(registry, "fetch_authorization_metadata", fetch)
    monkeypatch.setattr(registry, "register_dynamic_client", register)
    callback = base_url + "/api/connectors/oauth/callback"
    url, verifier, ctx = await registry.start_oauth_for_target(
        target={"type": "catalog", "kind": "qcc"},
        redirect_uri=callback,
        state="test-state",
        settings_repo=None,
    )
    fetch.assert_awaited_once_with(ISSUER)
    assert register.await_args.kwargs["redirect_uri"] == callback
    query = parse_qs(urlparse(url).query)
    assert url.startswith(f"{ISSUER}/oauth/authorize?")
    assert query["client_id"] == ["test-public-client"]
    assert query["redirect_uri"] == [callback]
    assert query["scope"] == ["mcp:tools"]
    assert query["resource"] == [RESOURCE]
    assert query["state"] == ["test-state"]
    assert query["code_challenge_method"] == ["S256"]
    challenge = urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert query["code_challenge"] == [challenge.decode()]
    assert ctx["issuer"] == ISSUER
    assert ctx["resource"] == RESOURCE


@pytest.mark.asyncio
async def test_qcc_refresh_uses_public_client_and_company_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = {"token_endpoint": f"{ISSUER}/oauth/token"}
    fetch = AsyncMock(return_value=metadata)
    refresh = AsyncMock(
        return_value={"access_token": "new-access", "refresh_token": "rotated-refresh"}
    )
    monkeypatch.setattr(registry, "fetch_authorization_metadata", fetch)
    monkeypatch.setattr(registry, "refresh_access_token", refresh)
    result = await registry.refresh_oauth_credentials(
        kind="qcc",
        creds={"oauth_client_id": "test-public-client", "refresh_token": "old-refresh"},
        settings_repo=None,
    )
    fetch.assert_awaited_once_with(ISSUER)
    refresh.assert_awaited_once_with(
        metadata,
        issuer=ISSUER,
        client_id="test-public-client",
        client_secret=None,
        refresh_token="old-refresh",
        resource=RESOURCE,
    )
    assert result["refresh_token"] == "rotated-refresh"
