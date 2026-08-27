"""Unit tests for MCP OAuth discovery and unified oauth targets."""

from __future__ import annotations

import pytest

from octop.infra.connectors.custom_mcp import (
    build_oauth_storage,
    harness_spec_for_server,
    merge_preserved_oauth,
    redact_server_for_api,
)
from octop.infra.connectors.oauth.discovery import (
    build_protected_resource_metadata_urls,
    parse_www_authenticate_resource_metadata,
)
from octop.infra.connectors.oauth.registry import (
    oauth_state_kind_for_target,
    oauth_target_requires_https,
)


def test_build_protected_resource_metadata_urls_path_and_root():
    urls = build_protected_resource_metadata_urls("https://example.com/mcp")
    assert urls == [
        "https://example.com/.well-known/oauth-protected-resource/mcp",
        "https://example.com/.well-known/oauth-protected-resource",
    ]


def test_build_protected_resource_metadata_urls_prefers_www_auth_header():
    header_url = "https://example.com/.well-known/oauth-protected-resource/custom"
    urls = build_protected_resource_metadata_urls(
        "https://example.com/mcp",
        www_auth_resource_metadata=header_url,
    )
    assert urls[0] == header_url


def test_parse_www_authenticate_resource_metadata():
    raw = 'Bearer error="invalid_token", resource_metadata="https://mcp.example.com/prm"'
    assert parse_www_authenticate_resource_metadata(raw) == "https://mcp.example.com/prm"


def test_oauth_target_helpers():
    assert oauth_state_kind_for_target({"type": "catalog", "kind": "notion"}) == "notion"
    assert oauth_state_kind_for_target({"type": "custom_mcp", "server_name": "x"}) == ("custom-mcp")
    assert oauth_target_requires_https({"type": "catalog", "kind": "notion"}) is True
    assert oauth_target_requires_https({"type": "custom_mcp", "server_name": "x"}) is True
    assert oauth_target_requires_https({"type": "catalog", "kind": "tencent-docs"}) is False


def test_merge_preserved_oauth_and_redaction():
    existing = {
        "srv": {
            "transport": "streamable_http",
            "url": "https://example.com/mcp",
            "oauth": {"access_token": "secret", "expires_at": 123},
        }
    }
    incoming = {
        "srv": {
            "transport": "streamable_http",
            "url": "https://example.com/mcp",
            "oauth": {"access_token": "client-sent"},
        }
    }
    merged = merge_preserved_oauth(incoming, existing)
    assert merged["srv"]["oauth"]["access_token"] == "secret"
    preview = redact_server_for_api(merged["srv"])
    assert preview["oauth"] == {"configured": True, "expires_at": 123}
    assert "access_token" not in preview["oauth"]


def test_oauth_required_hint_redaction_and_merge():
    existing = {
        "srv": {
            "transport": "streamable_http",
            "url": "https://example.com/mcp",
            "oauth": {"required": True},
        }
    }
    incoming = {"srv": {"transport": "streamable_http", "url": "https://example.com/mcp"}}
    merged = merge_preserved_oauth(incoming, existing)
    assert merged["srv"]["oauth"] == {"required": True}
    preview = redact_server_for_api(merged["srv"])
    assert preview["oauth"] == {"configured": False, "required": True}


def test_harness_spec_injects_oauth_bearer():
    spec = {
        "transport": "streamable_http",
        "url": "https://example.com/mcp",
        "oauth": build_oauth_storage(
            {"access_token": "tok123", "refresh_token": "r", "expires_at": 1},
            issuer="https://example.com",
            resource="https://example.com/mcp",
        ),
    }
    harness = harness_spec_for_server(spec)
    assert harness["headers"]["Authorization"] == "Bearer tok123"


def test_oauth_state_kind_invalid():
    with pytest.raises(ValueError, match="unsupported oauth target"):
        oauth_state_kind_for_target({"type": "unknown"})
