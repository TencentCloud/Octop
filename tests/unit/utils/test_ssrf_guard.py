"""Unit tests for SSRF guard (infra/utils/ssrf_guard.py)."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from octop.infra.utils.ssrf_guard import (
    ALLOW_HTTP_ENV,
    ALLOWLIST_ENV,
    UnsafeOutboundUrl,
    host_allowed_for_issuer,
    is_private_or_local_host,
    issuer_base_domain,
    safe_request,
    validate_https_url,
    validate_https_url_resolved,
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


@pytest.fixture
def no_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ALLOWLIST_ENV, raising=False)
    monkeypatch.delenv(ALLOW_HTTP_ENV, raising=False)


def _resolve_to(monkeypatch: pytest.MonkeyPatch, answers: dict[str, str]) -> None:
    real = socket.getaddrinfo

    def fake(host, port, *args, **kwargs):  # type: ignore[no-untyped-def]
        if host in answers:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (answers[host], port))]
        return real(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake)


@pytest.mark.usefixtures("no_allowlist")
@pytest.mark.parametrize("url", ["https://192.168.1.10/v1/audio", "http://192.168.1.10:8000/v1"])
def test_lan_targets_stay_blocked_without_allowlist(url: str) -> None:
    with pytest.raises(UnsafeOutboundUrl):
        validate_https_url(url)


@pytest.mark.usefixtures("no_allowlist")
def test_allowlisted_cidr_opens_only_that_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ALLOWLIST_ENV, "192.168.1.0/24")
    assert validate_https_url("https://192.168.1.10/v1/audio")
    for url in ("https://10.0.0.1/x", "https://169.254.169.254/latest/meta-data"):
        with pytest.raises(UnsafeOutboundUrl):
            validate_https_url(url)


@pytest.mark.usefixtures("no_allowlist")
def test_http_needs_the_switch_and_an_allowlisted_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ALLOWLIST_ENV, "192.168.1.0/24")
    with pytest.raises(UnsafeOutboundUrl, match="only https"):
        validate_https_url("http://192.168.1.10:8000/v1")

    monkeypatch.setenv(ALLOW_HTTP_ENV, "true")
    assert validate_https_url("http://192.168.1.10:8000/v1")
    with pytest.raises(UnsafeOutboundUrl, match="only https"):
        validate_https_url("http://mcp.example.com/v1")


@pytest.mark.usefixtures("no_allowlist")
async def test_allowlisted_name_may_resolve_to_a_lan_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ALLOWLIST_ENV, ".lan")
    _resolve_to(monkeypatch, {"whisper.lan": "192.168.1.20", "nas.example.com": "192.168.1.20"})
    assert await validate_https_url_resolved("https://whisper.lan/v1/audio")
    with pytest.raises(UnsafeOutboundUrl, match="private"):
        await validate_https_url_resolved("https://nas.example.com/v1/audio")


@pytest.fixture
def local_http_server() -> Iterator[tuple[int, list[str]]]:
    seen_hosts: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen_hosts.append(self.headers.get("host", ""))
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], seen_hosts
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.usefixtures("no_allowlist")
async def test_allowlisted_http_request_is_pinned_to_the_validated_ip(
    monkeypatch: pytest.MonkeyPatch, local_http_server: tuple[int, list[str]]
) -> None:
    port, seen_hosts = local_http_server
    monkeypatch.setenv(ALLOWLIST_ENV, ".lan")
    monkeypatch.setenv(ALLOW_HTTP_ENV, "1")
    # "whisper.lan" exists only in the validated answer; the request can only
    # reach the test server if the connection is pinned to that IP.
    _resolve_to(monkeypatch, {"whisper.lan": "127.0.0.1"})
    response = await safe_request("GET", f"http://whisper.lan:{port}/v1/models")
    assert response.status_code == 200
    assert seen_hosts == [f"whisper.lan:{port}"]
