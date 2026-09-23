"""QCC catalog integration with the shared MCP OAuth and probe flows."""

from __future__ import annotations

import hashlib
from base64 import urlsafe_b64encode
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest

from octop.config import OctopConfig
from octop.infra.connectors.builder import build_http_mcp_spec, validate_create_credentials
from octop.infra.connectors.catalog import get_mcp_oauth_remote
from octop.infra.connectors.oauth import registry
from octop.infra.connectors.probe import probe_connector

ISSUER = "https://agent.qcc.com"
RESOURCE = f"{ISSUER}/mcp/company/stream"


@pytest.mark.asyncio
async def test_qcc_credentials_build_and_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = get_mcp_oauth_remote("qcc")
    assert entry is not None
    creds = validate_create_credentials("qcc", {"access_token": "test-qcc-token"})
    creds["internal_token"] = "local-gateway-token"
    spec = build_http_mcp_spec(
        entry=entry, instance_id="qcc-test", creds=creds, config=OctopConfig()
    )
    assert "/api/internal/mcp/qcc/qcc-test?token=local-gateway-token" in spec["url"]
    assert "test-qcc-token" not in str(spec)
    probe = AsyncMock(return_value={"ok": True, "tools": []})
    monkeypatch.setattr("octop.infra.connectors.qcc.probe", probe)
    result = await probe_connector(entry, creds, instance_id="qcc-test", config=OctopConfig())
    assert result["ok"] is True
    probe.assert_awaited_once_with("test-qcc-token")


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata_scopes", [None, ["mcp:tools"]])
async def test_qcc_catalog_authorization_parameters(
    monkeypatch: pytest.MonkeyPatch, metadata_scopes: list[str] | None
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
    callback = "http://127.0.0.1:8088/api/connectors/oauth/callback"
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
