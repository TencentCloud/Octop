"""The discovery URL must follow RFC 8414 section 3.1 for path-scoped issuers."""

from __future__ import annotations

import asyncio

import pytest

from octop.infra.connectors.oauth import mcp


class _Resp:
    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {
            "issuer": requested["issuer"],
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
        }


requested: dict[str, str] = {}


@pytest.mark.parametrize(
    ("issuer", "expected"),
    [
        (
            "https://auth.example.com",
            "https://auth.example.com/.well-known/oauth-authorization-server",
        ),
        (
            "https://auth.example.com/realms/tenant",
            "https://auth.example.com/.well-known/oauth-authorization-server/realms/tenant",
        ),
        (
            "https://auth.example.com/realms/tenant/",
            "https://auth.example.com/.well-known/oauth-authorization-server/realms/tenant",
        ),
    ],
)
def test_metadata_url(issuer, expected, monkeypatch):
    seen: list[str] = []

    async def _safe_request(method, url, **kwargs):
        seen.append(url)
        requested["issuer"] = issuer
        return _Resp()

    async def _passthrough(url, **kwargs):
        return url

    monkeypatch.setattr(mcp, "safe_request", _safe_request)
    monkeypatch.setattr(mcp, "_ensure_mcp_oauth_url", _passthrough)
    monkeypatch.setattr(mcp, "_validate_metadata_endpoints", lambda data, **k: _pass(data))

    asyncio.run(mcp.fetch_authorization_metadata(issuer))

    assert seen[0] == expected


async def _pass(data):
    return data
