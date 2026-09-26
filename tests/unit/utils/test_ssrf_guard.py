"""Unit tests for SSRF guard (infra/utils/ssrf_guard.py)."""

from __future__ import annotations

import asyncio
import socket

import pytest

from octop.infra.utils.ssrf_guard import (
    UnsafeOutboundUrl,
    host_allowed_for_issuer,
    is_private_or_local_host,
    issuer_base_domain,
    validate_http_url,
    validate_http_url_resolved,
    validate_https_url,
)


def test_issuer_base_domain() -> None:
    assert issuer_base_domain("https://mcp.notion.com") == "notion.com"


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("localhost", True),
        ("127.0.0.1", True),
        ("::1", True),
        ("10.0.0.1", True),
        ("192.168.1.1", True),
        ("host.docker.internal", True),
        ("nas.local", True),
        ("mcp.example.com", False),
        ("8.8.8.8", False),
    ],
)
def test_is_private_or_local_host(host: str, expected: bool) -> None:
    assert is_private_or_local_host(host) is expected


@pytest.mark.parametrize(
    ("host", "issuer", "allowed"),
    [
        ("mcp.notion.com", "https://mcp.notion.com", True),
        ("api.notion.com", "https://mcp.notion.com", True),
        ("evil.com", "https://mcp.notion.com", False),
        ("notion.com.evil.com", "https://mcp.notion.com", False),
    ],
)
def test_host_allowed_for_issuer(host: str, issuer: str, allowed: bool) -> None:
    assert host_allowed_for_issuer(host, issuer) is allowed


@pytest.mark.parametrize(
    "url",
    [
        "http://mcp.notion.com/token",
        "https://127.0.0.1/token",
        "https://10.0.0.1/token",
        "https://localhost/token",
        "https://169.254.169.254/latest/meta-data",
    ],
)
def test_validate_https_url_rejects_unsafe_targets(url: str) -> None:
    with pytest.raises(UnsafeOutboundUrl):
        validate_https_url(url, field="token_endpoint")


def test_validate_https_url_accepts_public_host() -> None:
    assert (
        validate_https_url("https://mcp.notion.com/.well-known/oauth-authorization-server")
        == "https://mcp.notion.com/.well-known/oauth-authorization-server"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://10.182.12.254:8080/portal/index_phone.jsp",
        "https://127.0.0.1/private",
        "http://localhost:8080/private",
        "https://service.internal/private",
    ],
)
def test_validate_http_url_rejects_local_targets(url: str) -> None:
    with pytest.raises(UnsafeOutboundUrl):
        validate_http_url(url, field="url")


@pytest.mark.asyncio
async def test_validate_http_url_resolved_rejects_private_dns_result(monkeypatch) -> None:
    class FakeLoop:
        async def getaddrinfo(self, *args: object, **kwargs: object):
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    0,
                    "",
                    ("10.182.12.254", 8080),
                )
            ]

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: FakeLoop())

    with pytest.raises(UnsafeOutboundUrl, match="private or reserved"):
        await validate_http_url_resolved("http://public.example/private", field="url")
