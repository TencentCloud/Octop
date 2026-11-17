"""AS metadata URL must follow RFC 8414 §3.1 for path-scoped issuers."""

from __future__ import annotations

from typing import Any

import pytest

from octop.infra.connectors.oauth import mcp


class _Resp:
    def __init__(self, issuer: str) -> None:
        self._issuer = issuer

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {
            "issuer": self._issuer,
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
        }


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
        (
            "https://mcp.example.com/tenant/https%3A%2F%2Fapp.example.com",
            "https://mcp.example.com/.well-known/oauth-authorization-server"
            "/tenant/https%3A%2F%2Fapp.example.com",
        ),
    ],
)
@pytest.mark.asyncio
async def test_metadata_url_follows_rfc8414(
    issuer: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    async def _safe_request(method: str, url: str, **kwargs: Any) -> _Resp:
        del method, kwargs
        seen.append(url)
        return _Resp(issuer)

    async def _passthrough(url: str, **kwargs: Any) -> str:
        del kwargs
        return url

    async def _pass(data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        del kwargs
        return data

    monkeypatch.setattr(mcp, "safe_request", _safe_request)
    monkeypatch.setattr(mcp, "_ensure_mcp_oauth_url", _passthrough)
    monkeypatch.setattr(mcp, "_validate_metadata_endpoints", _pass)

    await mcp.fetch_authorization_metadata(issuer)

    assert seen == [expected]
