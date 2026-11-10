"""Pre-registered OAuth clients for custom MCP servers without dynamic registration."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from octop.infra.connectors.custom_mcp import (
    build_oauth_storage,
    harness_spec_for_server,
    merge_preserved_oauth,
    normalize_server_spec,
    redact_server_for_api,
)
from octop.infra.connectors.oauth import discovery as discovery_mod
from octop.infra.connectors.oauth import mcp as mcp_mod
from octop.infra.connectors.oauth import registry as registry_mod
from octop.infra.connectors.oauth.discovery import (
    clear_oauth_discovery_cache,
    discover_oauth_from_mcp_url,
)
from octop.infra.connectors.oauth.registry import (
    refresh_custom_mcp_oauth,
    start_custom_mcp_oauth,
)
from octop.infra.connectors.probe import _maybe_attach_oauth_discovery

MCP_URL = "https://mcp.example.com/mcp"
REDIRECT = "http://127.0.0.1:8088/api/connectors/oauth/callback"
AS_METADATA = {
    "issuer": "https://auth.example.com",
    "authorization_endpoint": "https://auth.example.com/authorize",
    "token_endpoint": "https://auth.example.com/token",
    "scopes_supported": ["read", "write"],
}
NO_REGISTRATION = {
    "available": False,
    "client_required": True,
    "error": "authorization server does not support dynamic client registration",
    "issuer": "https://auth.example.com",
    "resource": MCP_URL,
    "metadata": AS_METADATA,
    "scopes_supported": ["read", "write"],
}


def _server(**oauth_client: Any) -> dict[str, Any]:
    return {"transport": "streamable_http", "url": MCP_URL, "oauth_client": oauth_client}


def _query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def test_normalize_keeps_client_and_hides_it_from_the_harness() -> None:
    spec = normalize_server_spec(
        "srv",
        _server(client_id=" cid ", client_secret="shh", scope=" repo read:user ", junk="x"),
    )
    assert spec["oauth_client"] == {
        "client_id": "cid",
        "scope": "repo read:user",
        "client_secret": "shh",
    }
    assert "oauth_client" not in harness_spec_for_server(spec)


def test_normalize_drops_an_empty_client() -> None:
    spec = normalize_server_spec("srv", _server(client_id="", scope=""))
    assert "oauth_client" not in spec


@pytest.mark.parametrize(
    ("client", "message"),
    [
        ({"scope": "read"}, "client_id is required"),
        (
            {"client_id": "cid", "token_endpoint": "https://auth.example.com/token"},
            "both authorization_endpoint and token_endpoint",
        ),
        (
            {
                "client_id": "cid",
                "authorization_endpoint": "http://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
            },
            "only https",
        ),
        (
            {
                "client_id": "cid",
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://127.0.0.1/token",
            },
            "private or reserved",
        ),
    ],
)
def test_normalize_rejects_an_unusable_client(client: dict[str, str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_server_spec("srv", _server(**client))


def test_redaction_never_returns_the_client_secret() -> None:
    spec = normalize_server_spec("srv", _server(client_id="cid", client_secret="shh"))
    preview = redact_server_for_api(spec)
    assert preview["oauth_client"] == {"client_id": "cid", "has_client_secret": True}

    public = normalize_server_spec("srv", _server(client_id="cid"))
    assert redact_server_for_api(public)["oauth_client"] == {
        "client_id": "cid",
        "has_client_secret": False,
    }


def test_saving_the_redacted_preview_back_keeps_secret_and_tokens() -> None:
    stored = normalize_server_spec("srv", _server(client_id="cid", client_secret="shh"))
    stored["oauth"] = build_oauth_storage(
        {"access_token": "tok", "oauth_client_id": "cid"},
        issuer="https://auth.example.com",
        resource=None,
    )
    echoed = redact_server_for_api(stored)

    merged = merge_preserved_oauth({"srv": echoed}, {"srv": stored})

    assert merged["srv"]["oauth_client"] == {"client_id": "cid", "client_secret": "shh"}
    assert merged["srv"]["oauth"]["access_token"] == "tok"


@pytest.mark.parametrize(
    "incoming_client",
    [
        {"client_id": "other"},
        {"client_id": "cid", "client_secret": "rotated"},
        {"client_id": "cid", "client_secret": ""},
        {"client_id": "cid", "scope": "admin"},
        None,
    ],
)
def test_changing_the_client_asks_for_authorization_again(
    incoming_client: dict[str, str] | None,
) -> None:
    stored = normalize_server_spec("srv", _server(client_id="cid", client_secret="shh"))
    stored["oauth"] = {"access_token": "tok", "oauth_client_id": "cid"}
    incoming: dict[str, Any] = {"transport": "streamable_http", "url": MCP_URL}
    if incoming_client is not None:
        incoming["oauth_client"] = incoming_client

    merged = merge_preserved_oauth({"srv": incoming}, {"srv": stored})

    assert merged["srv"]["oauth"] == {"required": True}


def test_a_new_client_id_does_not_inherit_the_old_secret() -> None:
    stored = normalize_server_spec("srv", _server(client_id="cid", client_secret="shh"))
    merged = merge_preserved_oauth(
        {"srv": _server(client_id="other")},
        {"srv": stored},
    )
    assert merged["srv"]["oauth_client"] == {"client_id": "other"}


@pytest.mark.asyncio
async def test_discovery_reports_client_required_without_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_oauth_discovery_cache()

    async def no_challenge(url: str) -> None:
        return None

    async def prm(url: str) -> dict[str, Any]:
        return {"resource": MCP_URL, "authorization_servers": ["https://auth.example.com"]}

    async def metadata(issuer: str) -> dict[str, Any]:
        return dict(AS_METADATA)

    monkeypatch.setattr(discovery_mod, "_probe_401_resource_metadata", no_challenge)
    monkeypatch.setattr(discovery_mod, "_fetch_prm_document", prm)
    monkeypatch.setattr(discovery_mod, "fetch_authorization_metadata", metadata)

    found = await discover_oauth_from_mcp_url(MCP_URL, use_cache=False)

    assert found["available"] is False
    assert found["client_required"] is True
    assert found["issuer"] == "https://auth.example.com"
    assert found["metadata"]["token_endpoint"] == "https://auth.example.com/token"


async def _no_registration(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise AssertionError("a pre-registered client must not register dynamically")


@pytest.mark.asyncio
async def test_start_uses_the_saved_client_instead_of_registering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry_mod, "register_dynamic_client", _no_registration)

    url, verifier, ctx = await start_custom_mcp_oauth(
        server_name="srv",
        mcp_url=MCP_URL,
        redirect_uri=REDIRECT,
        state="st",
        discovery=NO_REGISTRATION,
        oauth_client={"client_id": "cid", "client_secret": "shh"},
    )

    query = _query(url)
    assert url.startswith("https://auth.example.com/authorize?")
    assert query["client_id"] == "cid"
    assert query["redirect_uri"] == REDIRECT
    assert query["code_challenge_method"] == "S256"
    assert query["scope"] == "read write"
    assert query["resource"] == MCP_URL
    assert verifier
    assert ctx["client_id"] == "cid"
    assert ctx["client_secret"] == "shh"
    assert ctx["issuer"] == "https://auth.example.com"
    assert "token_endpoint" not in ctx


@pytest.mark.asyncio
async def test_start_prefers_the_client_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry_mod, "register_dynamic_client", _no_registration)

    url, _, _ = await start_custom_mcp_oauth(
        server_name="srv",
        mcp_url=MCP_URL,
        redirect_uri=REDIRECT,
        state="st",
        discovery=NO_REGISTRATION,
        oauth_client={"client_id": "cid", "scope": "repo"},
    )

    assert _query(url)["scope"] == "repo"


@pytest.mark.asyncio
async def test_start_with_explicit_endpoints_skips_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_discovery(url: str) -> dict[str, Any]:
        raise AssertionError("explicit endpoints must not trigger discovery")

    async def public(url: str, *, field: str = "url") -> str:
        return url

    monkeypatch.setattr(registry_mod, "register_dynamic_client", _no_registration)
    monkeypatch.setattr(registry_mod, "discover_oauth_from_mcp_url", no_discovery)
    monkeypatch.setattr(mcp_mod, "validate_https_url_resolved", public)

    url, _, ctx = await start_custom_mcp_oauth(
        server_name="srv",
        mcp_url=MCP_URL,
        redirect_uri=REDIRECT,
        state="st",
        oauth_client={
            "client_id": "cid",
            "authorization_endpoint": "https://accounts.example.com/o/authorize",
            "token_endpoint": "https://oauth2.example-apis.com/token",
        },
    )

    query = _query(url)
    assert url.startswith("https://accounts.example.com/o/authorize?")
    assert query["client_id"] == "cid"
    assert "resource" not in query
    assert "scope" not in query
    assert ctx["issuer"] == "https://oauth2.example-apis.com"
    assert ctx["token_endpoint"] == "https://oauth2.example-apis.com/token"
    assert ctx["resource"] is None


@pytest.mark.asyncio
async def test_start_without_a_client_still_needs_registration() -> None:
    with pytest.raises(ValueError, match="dynamic client registration"):
        await start_custom_mcp_oauth(
            server_name="srv",
            mcp_url=MCP_URL,
            redirect_uri=REDIRECT,
            state="st",
            discovery=NO_REGISTRATION,
        )


@pytest.mark.asyncio
async def test_start_names_the_endpoints_when_nothing_is_discoverable() -> None:
    with pytest.raises(ValueError, match="authorization_endpoint and token_endpoint"):
        await start_custom_mcp_oauth(
            server_name="srv",
            mcp_url=MCP_URL,
            redirect_uri=REDIRECT,
            state="st",
            discovery={"available": False, "error": "protected resource metadata not found"},
            oauth_client={"client_id": "cid"},
        )


@pytest.mark.asyncio
async def test_refresh_uses_the_remembered_token_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    async def no_metadata(issuer: str) -> dict[str, Any]:
        raise AssertionError("a remembered token endpoint must not be rediscovered")

    async def fake_refresh(metadata: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        seen["metadata"] = metadata
        seen.update(kwargs)
        return {"access_token": "new", "refresh_token": "r2", "expires_at": 42}

    monkeypatch.setattr(registry_mod, "fetch_authorization_metadata", no_metadata)
    monkeypatch.setattr(registry_mod, "refresh_access_token", fake_refresh)
    stored = build_oauth_storage(
        {
            "access_token": "old",
            "refresh_token": "r1",
            "oauth_client_id": "cid",
            "oauth_client_secret": "shh",
            "oauth_token_endpoint": "https://oauth2.example-apis.com/token",
        },
        issuer="https://oauth2.example-apis.com",
        resource=None,
    )

    refreshed = await refresh_custom_mcp_oauth(stored)

    assert seen["metadata"] == {"token_endpoint": "https://oauth2.example-apis.com/token"}
    assert seen["client_id"] == "cid"
    assert seen["client_secret"] == "shh"
    assert refreshed["access_token"] == "new"
    assert refreshed["oauth_token_endpoint"] == "https://oauth2.example-apis.com/token"


@pytest.mark.asyncio
async def test_token_requests_ask_for_json(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class _Response:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"access_token": "tok", "token_type": "bearer"}

    async def fake_request(method: str, url: str, **kwargs: Any) -> _Response:
        seen["headers"] = kwargs["headers"]
        return _Response()

    async def allowed(url: str, *, issuer: str, field: str) -> str:
        return url

    monkeypatch.setattr(mcp_mod, "safe_request", fake_request)
    monkeypatch.setattr(mcp_mod, "_ensure_mcp_oauth_url", allowed)

    tokens = await mcp_mod.exchange_authorization_code(
        {"token_endpoint": "https://auth.example.com/token"},
        issuer="https://auth.example.com",
        client_id="cid",
        client_secret="shh",
        code="code",
        redirect_uri=REDIRECT,
        code_verifier="verifier",
    )

    assert tokens["access_token"] == "tok"
    assert seen["headers"]["Accept"] == "application/json"


@pytest.mark.asyncio
@pytest.mark.parametrize(("client", "available"), [(None, False), ({"client_id": "cid"}, True)])
async def test_probe_marks_client_required(
    monkeypatch: pytest.MonkeyPatch,
    client: dict[str, str] | None,
    available: bool,
) -> None:
    async def discovered(url: str) -> dict[str, Any]:
        return NO_REGISTRATION

    monkeypatch.setattr("octop.infra.connectors.probe.discover_oauth_from_mcp_url", discovered)

    result = await _maybe_attach_oauth_discovery(
        {"ok": False, "error_type": "auth"},
        url=MCP_URL,
        headers={},
        oauth_client=client,
    )

    assert result["oauth"] == {
        "available": available,
        "client_required": True,
        "issuer": "https://auth.example.com",
        "resource": MCP_URL,
    }


@pytest.mark.asyncio
async def test_probe_with_explicit_endpoints_needs_no_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_discovery(url: str) -> dict[str, Any]:
        raise AssertionError("explicit endpoints must not trigger discovery")

    monkeypatch.setattr("octop.infra.connectors.probe.discover_oauth_from_mcp_url", no_discovery)

    result = await _maybe_attach_oauth_discovery(
        {"ok": False, "error_type": "auth"},
        url=MCP_URL,
        headers={},
        oauth_client={
            "client_id": "cid",
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
        },
    )

    assert result["oauth"] == {"available": True}
