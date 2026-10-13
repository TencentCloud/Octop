"""Unit tests for SSRF guard (infra/utils/ssrf_guard.py)."""

from __future__ import annotations

import pytest

from octop.infra.utils.ssrf_guard import (
    UnsafeOutboundUrl,
    host_allowed_for_issuer,
    is_private_or_local_host,
    issuer_base_domain,
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
