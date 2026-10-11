"""MCP OAuth discovery must bind the metadata to the requested issuer (RFC 8414 3.3)."""

from __future__ import annotations

import asyncio

import pytest

from octop.infra.connectors.oauth import mcp


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def _metadata(issuer):
    return {
        "issuer": issuer,
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
    }


@pytest.mark.parametrize("returned", ["https://auth.example.com/other-tenant", "", None])
def test_missing_or_mismatched_issuer_is_rejected(returned, monkeypatch):
    payload = _metadata(returned)
    monkeypatch.setattr(mcp, "safe_request", lambda *a, **k: _await(_Resp(payload)))
    monkeypatch.setattr(mcp, "_ensure_mcp_oauth_url", lambda url, **k: _await(url))
    monkeypatch.setattr(mcp, "_validate_metadata_endpoints", lambda data, **k: _await(data))

    with pytest.raises(ValueError):
        asyncio.run(mcp.fetch_authorization_metadata("https://auth.example.com"))


def test_a_matching_issuer_is_accepted(monkeypatch):
    payload = _metadata("https://auth.example.com")
    monkeypatch.setattr(mcp, "safe_request", lambda *a, **k: _await(_Resp(payload)))
    monkeypatch.setattr(mcp, "_ensure_mcp_oauth_url", lambda url, **k: _await(url))
    monkeypatch.setattr(mcp, "_validate_metadata_endpoints", lambda data, **k: _await(data))

    assert asyncio.run(mcp.fetch_authorization_metadata("https://auth.example.com")) == payload


async def _await(value):
    return value
