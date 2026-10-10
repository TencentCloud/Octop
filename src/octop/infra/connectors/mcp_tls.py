"""Per-connector certificate trust for custom HTTPS MCP servers."""

from __future__ import annotations

import ssl

import httpx
from mcp.shared._httpx_utils import (
    MCP_DEFAULT_SSE_READ_TIMEOUT,
    MCP_DEFAULT_TIMEOUT,
    McpHttpClientFactory,
)

from octop.infra.errors import ErrorCode, OctopError

MAX_CA_CERT_BYTES = 64 * 1024


def normalize_ca_cert(value: object) -> str:
    """Validate an uploaded PEM certificate/bundle without accepting private keys."""
    try:
        if not isinstance(value, str):
            raise ValueError("certificate must be PEM text")
        pem = value.strip()
        if (
            not pem
            or len(pem.encode("ascii")) > MAX_CA_CERT_BYTES
            or "PRIVATE KEY" in pem
            or not pem.startswith("-----BEGIN CERTIFICATE-----")
        ):
            raise ValueError("invalid certificate file")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=pem)
    except (ValueError, ssl.SSLError) as exc:
        raise OctopError(
            ErrorCode.CONNECTOR_MCP_CERT_INVALID,
            "invalid custom MCP certificate",
        ) from exc
    return pem


def certificate_client_factory(ca_cert: str) -> McpHttpClientFactory:
    """Add this connector's CA to normal HTTPX trust, retaining hostname validation."""

    def create_client(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.AsyncClient:
        context = httpx.create_ssl_context()
        context.load_verify_locations(cadata=ca_cert)
        return httpx.AsyncClient(
            verify=context,
            headers=headers,
            timeout=timeout
            or httpx.Timeout(MCP_DEFAULT_TIMEOUT, read=MCP_DEFAULT_SSE_READ_TIMEOUT),
            auth=auth,
            follow_redirects=True,
        )

    return create_client
