"""Authorization endpoints retain their existing query during MCP OAuth."""

from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest

from octop.infra.connectors.oauth import registry
from octop.infra.connectors.oauth.mcp import build_authorize_url
from octop.infra.connectors.oauth.pkce import s256_challenge

ENDPOINT = "https://auth.example.com/authorize"
CALLBACK = "https://octop.example.com/callback?from=mcp"
RESOURCE = "https://mcp.example.com/tools"


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "?",
        "?tenant=acme",
        "?tenant=acme&prompt=consent",
        "?tenant=acme%20corp&hint=a%2Bb",
        "?tenant=",
        "?tenant=acme&tenant=beta",
    ],
)
@pytest.mark.parametrize("optional", [False, True])
def test_authorize_url_retains_endpoint_query(suffix: str, optional: bool) -> None:
    params = {
        "client_id": "test-client",
        "redirect_uri": CALLBACK,
        "state": "state +/?",
        "code_challenge": "challenge",
    }
    if optional:
        params.update(scope="tools:read tools:write", resource=RESOURCE)
    url = build_authorize_url({"authorization_endpoint": ENDPOINT + suffix}, **params)
    parsed = urlsplit(url)
    original = urlsplit(ENDPOINT + suffix).query
    assert (parsed.scheme, parsed.netloc, parsed.path) == (
        "https",
        "auth.example.com",
        "/authorize",
    )
    if original:
        assert parsed.query.startswith(original + "&")
    expected = parse_qs(original, keep_blank_values=True)
    expected.update({key: [value] for key, value in params.items()})
    expected.update(response_type=["code"], code_challenge_method=["S256"])
    assert parse_qs(parsed.query, keep_blank_values=True) == expected


@pytest.mark.asyncio
async def test_custom_mcp_oauth_retains_discovered_query(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = {
        "authorization_endpoint": ENDPOINT + "?tenant=acme%20corp",
        "scopes_supported": ["tools:read", "tools:write"],
    }
    discovery = AsyncMock(
        return_value={
            "available": True,
            "issuer": "https://auth.example.com",
            "resource": RESOURCE,
            "metadata": metadata,
        }
    )
    register = AsyncMock(return_value={"client_id": "test-client"})
    monkeypatch.setattr(registry, "discover_oauth_from_mcp_url", discovery)
    monkeypatch.setattr(registry, "register_dynamic_client", register)
    url, verifier, ctx = await registry.start_custom_mcp_oauth(
        server_name="example",
        mcp_url=RESOURCE,
        redirect_uri=CALLBACK,
        state="test-state",
    )
    discovery.assert_awaited_once_with(RESOURCE)
    register.assert_awaited_once_with(
        metadata,
        issuer="https://auth.example.com",
        redirect_uri=CALLBACK,
    )
    query = urlsplit(url).query
    assert query.startswith("tenant=acme%20corp&")
    assert parse_qs(query) == {
        "tenant": ["acme corp"],
        "response_type": ["code"],
        "client_id": ["test-client"],
        "redirect_uri": [CALLBACK],
        "state": ["test-state"],
        "code_challenge": [s256_challenge(verifier)],
        "code_challenge_method": ["S256"],
        "scope": ["tools:read tools:write"],
        "resource": [RESOURCE],
    }
    assert ctx["metadata"] == metadata
    assert ctx["server_name"] == "example"
