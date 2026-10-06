"""Uploaded certificates must work in probes and real MCP sessions, with TLS checks intact."""

from __future__ import annotations

import asyncio
import json
import ssl
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from langchain_mcp_adapters.sessions import create_session
from tests.support.certificates import make_test_certificate

from octop.infra.connectors.custom_mcp import harness_spec_for_server, normalize_server_spec
from octop.infra.connectors.mcp_tls import MAX_CA_CERT_BYTES, normalize_ca_cert
from octop.infra.connectors.probe import probe_custom_mcp_server
from octop.infra.errors import ErrorCode, OctopError


@asynccontextmanager
async def tls_mcp_server(material):
    """Serve minimal stateless MCP over a real TLS socket."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(material.cert_file, material.key_file)

    async def handle(reader, writer):
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            headers = dict(line.split(b":", 1) for line in head.split(b"\r\n")[1:] if b":" in line)
            length = next((int(v) for k, v in headers.items() if k.lower() == b"content-length"), 0)
            request = json.loads(await reader.readexactly(length)) if length else {}
            method = request.get("method")
            if method == "initialize":
                result = {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "tls-test", "version": "1"},
                }
            elif method == "tools/list":
                result = {
                    "tools": [{"name": "ping", "inputSchema": {"type": "object", "properties": {}}}]
                }
            elif method == "tools/call":
                result = {"content": [{"type": "text", "text": "pong"}]}
            else:
                result = None
            body = (
                json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}).encode()
                if "id" in request
                else b""
            )
            status = "200 OK" if body else "202 Accepted"
            writer.write(
                f"HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                + body
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=context)
    async with server:
        yield f"https://127.0.0.1:{server.sockets[0].getsockname()[1]}/mcp"


@pytest.mark.parametrize("self_signed", [False, True])
async def test_uploaded_certificate_works_for_probe_and_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, self_signed: bool
):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    material = make_test_certificate(tmp_path, self_signed=self_signed)
    async with tls_mcp_server(material) as url:
        spec = {"transport": "streamable_http", "url": url}
        untrusted = await probe_custom_mcp_server(spec)
        assert untrusted["ok"] is False
        assert "CERTIFICATE_VERIFY_FAILED" in untrusted["error"]

        spec["ca_cert"] = material.ca_pem
        normalized = normalize_server_spec("private", spec)
        result = await probe_custom_mcp_server(normalized)
        assert result["ok"] is True
        assert result["tools"] == [{"name": "ping", "description": ""}]

        connection = harness_spec_for_server(normalized)
        assert "ca_cert" not in connection
        async with create_session(connection) as session:
            response = await session.call_tool("ping")
            assert response.content[0].text == "pong"

        # The uploaded CA must not leak into another connector's default trust.
        assert "httpx_client_factory" not in harness_spec_for_server(
            {"transport": "streamable_http", "url": url}
        )
        assert (await probe_custom_mcp_server({"transport": "streamable_http", "url": url}))[
            "ok"
        ] is False


@pytest.mark.parametrize("failure", ["wrong_ca", "wrong_host", "expired"])
async def test_uploaded_ca_keeps_tls_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    material = make_test_certificate(
        tmp_path / "server", wrong_host=failure == "wrong_host", expired=failure == "expired"
    )
    ca_pem = (
        make_test_certificate(tmp_path / "other").ca_pem
        if failure == "wrong_ca"
        else material.ca_pem
    )
    async with tls_mcp_server(material) as url:
        result = await probe_custom_mcp_server(
            {"transport": "streamable_http", "url": url, "ca_cert": ca_pem}
        )
        assert result["ok"] is False
        assert "CERTIFICATE_VERIFY_FAILED" in result["error"]


@pytest.mark.parametrize(
    "invalid",
    [
        "not a certificate",
        123,
        "x" * (MAX_CA_CERT_BYTES + 1),
        "-----BEGIN CERTIFICATE-----\nbroken\n-----END CERTIFICATE-----",
    ],
)
def test_rejects_invalid_certificate(invalid):
    with pytest.raises(OctopError) as exc:
        normalize_ca_cert(invalid)
    assert exc.value.code is ErrorCode.CONNECTOR_MCP_CERT_INVALID


def test_rejects_private_key_and_plain_http(tmp_path: Path):
    material = make_test_certificate(tmp_path)
    with pytest.raises(OctopError):
        normalize_ca_cert(material.ca_pem + material.key_file.read_text())
    with pytest.raises(OctopError):
        normalize_server_spec(
            "plain",
            {
                "transport": "streamable_http",
                "url": "http://127.0.0.1/mcp",
                "ca_cert": material.ca_pem,
            },
        )
