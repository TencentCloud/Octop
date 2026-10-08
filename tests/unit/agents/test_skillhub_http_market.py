"""Tests for direct HTTP SkillHub search and package installation."""

from __future__ import annotations

import io
import json
import socket
import ssl
import stat
import threading
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from octop.infra.skills import skillhub_market


class _BytesResponse:
    def __init__(self, payload: bytes, *, headers: dict[str, str] | None = None) -> None:
        self._stream = io.BytesIO(payload)
        self.headers = headers or {}

    def __enter__(self) -> _BytesResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


def _zip_bytes(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_search_skillhub_uses_http_api_and_preserves_rich_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    payload = {
        "results": [
            {
                "slug": "pdf-reader",
                "displayName": "PDF 阅读器",
                "summary": "读取 PDF",
                "version": "1.2.3",
                "iconUrl": "https://cdn.example.com/pdf.png",
                "description_zh": "中文说明",
                "downloads": 42,
            }
        ]
    }

    def fake_urlopen(request: Any, timeout: float) -> _BytesResponse:
        seen["url"] = request.full_url
        seen["accept"] = request.headers["Accept"]
        seen["timeout"] = timeout
        return _BytesResponse(json.dumps(payload).encode())

    monkeypatch.setattr(skillhub_market, "_urlopen", fake_urlopen)

    result = skillhub_market._fetch_search_json(
        "https://api.example.com",
        "PDF 中文",
        limit=12,
        timeout=7,
    )

    parsed = urllib.parse.urlparse(seen["url"])
    assert parsed.path == "/api/v1/search"
    assert urllib.parse.parse_qs(parsed.query) == {"q": ["PDF 中文"], "limit": ["12"]}
    assert seen["accept"] == "application/json"
    assert seen["timeout"] == 7
    assert result == [
        {
            "slug": "pdf-reader",
            "displayName": "PDF 阅读器",
            "name": "PDF 阅读器",
            "summary": "读取 PDF",
            "description": "读取 PDF",
            "version": "1.2.3",
            "iconUrl": "https://cdn.example.com/pdf.png",
            "description_zh": "中文说明",
            "downloads": 42,
        }
    ]


def test_download_skillhub_package_follows_endpoint_and_strips_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    payload = _zip_bytes(
        {
            "wrapped/SKILL.md": "---\nname: demo\n---\n",
            "wrapped/references/readme.txt": "hello",
        }
    )

    def fake_urlopen(request: Any, timeout: float) -> _BytesResponse:
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return _BytesResponse(payload, headers={"Content-Length": str(len(payload))})

    monkeypatch.setattr(skillhub_market, "_urlopen", fake_urlopen)

    files = skillhub_market._download_skillhub_package(
        "https://api.example.com",
        "demo skill",
        timeout=9,
    )

    parsed = urllib.parse.urlparse(seen["url"])
    assert parsed.path == "/api/v1/download"
    assert urllib.parse.parse_qs(parsed.query) == {"slug": ["demo skill"]}
    assert seen["timeout"] == 9
    assert dict(files) == {
        "SKILL.md": b"---\nname: demo\n---\n",
        "references/readme.txt": b"hello",
    }


def test_parse_skillhub_package_repairs_invalid_utf8_in_skill_md() -> None:
    corrupted = "---\nname: humanizer\n---\n每句 ".encode() + b"\xe2j$" + "15 字\n".encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SKILL.md", corrupted)

    files = dict(skillhub_market.parse_skillhub_package(buffer.getvalue()))

    assert files["SKILL.md"].decode("utf-8") == "---\nname: humanizer\n---\n每句 ≤15 字\n"


def test_parse_skillhub_package_rejects_unrepairable_skill_md() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SKILL.md", b"---\nname: bad\n---\n\xff\xfe broken")

    with pytest.raises(skillhub_market.SkillHubPackageError, match="not valid UTF-8"):
        skillhub_market.parse_skillhub_package(buffer.getvalue())


@pytest.mark.parametrize(
    "filename",
    [
        "../escape.txt",
        "/absolute.txt",
        "folder\\..\\escape.txt",
        "C:/windows.txt",
    ],
)
def test_parse_skillhub_package_rejects_unsafe_paths(filename: str) -> None:
    payload = _zip_bytes(
        {
            "SKILL.md": "---\nname: demo\n---\n",
            filename: "unsafe",
        }
    )

    with pytest.raises(skillhub_market.SkillHubPackageError, match="zip path"):
        skillhub_market.parse_skillhub_package(payload)


def test_parse_skillhub_package_rejects_symlinks() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SKILL.md", "---\nname: demo\n---\n")
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "SKILL.md")

    with pytest.raises(skillhub_market.SkillHubPackageError, match="entry type"):
        skillhub_market.parse_skillhub_package(buffer.getvalue())


def test_parse_skillhub_package_requires_root_manifest() -> None:
    payload = _zip_bytes({"README.md": "not a skill"})

    with pytest.raises(skillhub_market.SkillHubPackageError, match="root SKILL.md"):
        skillhub_market.parse_skillhub_package(payload)


def test_parse_skillhub_package_enforces_uncompressed_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skillhub_market, "_MAX_ZIP_UNCOMPRESSED_BYTES", 8)
    payload = _zip_bytes({"SKILL.md": "123456789"})

    with pytest.raises(skillhub_market.SkillHubPackageTooLarge, match="exceeds"):
        skillhub_market.parse_skillhub_package(payload)


def test_http_request_rejects_oversized_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(_request: Any, timeout: float) -> _BytesResponse:
        return _BytesResponse(b"", headers={"Content-Length": "101"})

    monkeypatch.setattr(skillhub_market, "_urlopen", fake_urlopen)

    with pytest.raises(skillhub_market.SkillHubPackageTooLarge, match="exceeds"):
        skillhub_market._http_request(
            "https://api.example.com/file",
            accept="application/zip",
            timeout=1,
            max_bytes=100,
        )


def test_fetch_ranking_json_rejects_oversized_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skillhub_market, "_MAX_JSON_BYTES", 16)

    def fake_urlopen(_request: Any, timeout: float) -> _BytesResponse:
        return _BytesResponse(b'{"section": "hot"}', headers={"Content-Length": "999"})

    monkeypatch.setattr(skillhub_market, "_urlopen", fake_urlopen)

    with pytest.raises(skillhub_market.SkillHubPackageTooLarge, match="exceeds"):
        skillhub_market._fetch_ranking_json("https://api.example.com", "hot", timeout=3)


def test_fetch_ranking_json_caps_chunked_body_without_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skillhub_market, "_MAX_JSON_BYTES", 16)

    def fake_urlopen(_request: Any, timeout: float) -> _BytesResponse:
        return _BytesResponse(b'{"skills": [' + b"0" * 64 + b"]}")

    monkeypatch.setattr(skillhub_market, "_urlopen", fake_urlopen)

    with pytest.raises(skillhub_market.SkillHubPackageTooLarge, match="exceeds"):
        skillhub_market._fetch_ranking_json("https://api.example.com", "hot", timeout=3)


def test_fetch_ranking_json_wraps_stream_reset_as_market_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dropped connection must surface as ``SkillHubMarketError``.

    ``/skills/hub/rankings`` only maps ``SkillHubMarketError`` (502) and
    ``SkillHubMarketTimeout`` (504); a bare ``OSError`` escaping here turns a
    retryable upstream hiccup into an opaque 500.
    """

    class _ResettingResponse(_BytesResponse):
        def read(self, size: int = -1) -> bytes:
            raise ConnectionResetError("connection reset by peer")

    def fake_urlopen(_request: Any, timeout: float) -> _ResettingResponse:
        return _ResettingResponse(b"")

    monkeypatch.setattr(skillhub_market, "_urlopen", fake_urlopen)

    with pytest.raises(skillhub_market.SkillHubMarketError) as excinfo:
        skillhub_market._fetch_ranking_json("https://api.example.com", "hot", timeout=3)
    assert not isinstance(excinfo.value, skillhub_market.SkillHubPackageError)


# --- Multi-address fallback (issue #1819) ------------------------------------
#
# SkillHub downloads 302-redirect to multi-IPv4 Tencent COS accelerate hosts.
# The urllib default only retries the next address while the TCP connect
# fails, so a CDN address whose TLS handshake stalls or gets reset fails the
# whole request even when another address works. These tests pin
# ``socket.getaddrinfo`` to a bad address first plus a healthy loopback server
# (matching the issue's reproduction) and assert the request still succeeds.


def _make_tls_credentials(
    tmp_path: Path,
    hostnames: tuple[str, ...],
) -> tuple[Path, Path]:
    """Self-signed certificate + key, valid for ``hostnames`` as a trust anchor."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostnames[0])])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(host) for host in hostnames]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "skillhub-test.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path = tmp_path / "skillhub-test.key"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


class _LocalServer:
    """Loopback server standing in for one SkillHub / CDN address."""

    def __init__(
        self,
        handler: type[BaseHTTPRequestHandler],
        *,
        tls: tuple[Path, Path] | None = None,
    ) -> None:
        self.sni: list[str] = []
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        if tls is not None:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=tls[0], keyfile=tls[1])
            context.sni_callback = lambda _sock, name, _ctx: self.sni.append(str(name))
            self._httpd.socket = context.wrap_socket(self._httpd.socket, server_side=True)
        self.port = int(self._httpd.server_address[1])
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


class _StalledAddress:
    """Listen socket that completes TCP but never answers the TLS hello.

    Mirrors the reported CDN nodes: reachable enough to accept the connection,
    after which the TLS handshake stalls until the request timeout.
    """

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.port = int(self._sock.getsockname()[1])

    def close(self) -> None:
        self._sock.close()


def _zip_handler(payload: bytes, hosts: list[str]) -> type[BaseHTTPRequestHandler]:
    class _ZipHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            hosts.append(self.headers.get("Host") or "")
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return _ZipHandler


def _redirect_handler(location: str) -> type[BaseHTTPRequestHandler]:
    class _RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return _RedirectHandler


class _SkillHubTestNet:
    """Loopback stand-in for SkillHub: HTTPS servers, stalled addresses, DNS."""

    HOSTS = ("api.skillhub.test", "cdn.skillhub.test")

    def __init__(self, tmp_path: Path) -> None:
        self._cert, self._key = _make_tls_credentials(tmp_path, self.HOSTS)
        self._servers: list[_LocalServer] = []
        self._stalled: list[_StalledAddress] = []

    def tls_server(self, handler: type[BaseHTTPRequestHandler]) -> _LocalServer:
        server = _LocalServer(handler, tls=(self._cert, self._key))
        self._servers.append(server)
        return server

    def plain_server(self, handler: type[BaseHTTPRequestHandler]) -> _LocalServer:
        server = _LocalServer(handler)
        self._servers.append(server)
        return server

    def stalled_address(self) -> int:
        address = _StalledAddress()
        self._stalled.append(address)
        return address.port

    def trust_context(self) -> ssl.SSLContext:
        return ssl.create_default_context(cafile=str(self._cert))

    def close(self) -> None:
        for server in self._servers:
            server.close()
        for address in self._stalled:
            address.close()


@pytest.fixture
def skillhub_net(tmp_path: Path) -> Iterator[_SkillHubTestNet]:
    net = _SkillHubTestNet(tmp_path)
    try:
        yield net
    finally:
        net.close()


def _install_test_network(
    monkeypatch: pytest.MonkeyPatch,
    net: _SkillHubTestNet,
    addresses: dict[str, list[tuple[str, int]]],
) -> None:
    """Pin DNS answers for the fake hosts and trust the loopback test CA."""
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(
        host: str | bytes | None,
        port: str | int | None,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[Any]:
        name = host.decode() if isinstance(host, bytes) else str(host)
        pinned = addresses.get(name)
        if pinned is not None:
            return [
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", address)
                for address in pinned
            ]
        return real_getaddrinfo(host, port, family, type, proto, flags)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    # A loopback server cannot present a publicly trusted certificate, so the
    # only substituted piece is the TLS trust store; the handler and the
    # connection class under test are the production ones.
    context = net.trust_context()
    monkeypatch.setattr(skillhub_market, "_shared_opener", None)
    monkeypatch.setattr(
        skillhub_market,
        "_build_opener",
        lambda: urllib.request.build_opener(skillhub_market._FallbackHTTPSHandler(context=context)),
    )


def test_download_falls_back_to_next_address_after_tls_stall(
    monkeypatch: pytest.MonkeyPatch,
    skillhub_net: _SkillHubTestNet,
) -> None:
    """Bad address first: the stalled handshake must not fail the request."""
    payload = _zip_bytes({"SKILL.md": "---\nname: demo\n---\n"})
    hosts: list[str] = []
    good = skillhub_net.tls_server(_zip_handler(payload, hosts))
    _install_test_network(
        monkeypatch,
        skillhub_net,
        {
            "api.skillhub.test": [
                ("127.0.0.1", skillhub_net.stalled_address()),
                ("127.0.0.1", good.port),
            ]
        },
    )

    files = skillhub_market.download_skillhub_package_files(
        "demo",
        host="https://api.skillhub.test",
        timeout=1.0,
    )

    assert dict(files) == {"SKILL.md": b"---\nname: demo\n---\n"}
    assert hosts == ["api.skillhub.test"]
    assert good.sni == ["api.skillhub.test"]


def test_download_falls_back_when_address_fails_tls_immediately(
    monkeypatch: pytest.MonkeyPatch,
    skillhub_net: _SkillHubTestNet,
) -> None:
    """A non-TLS answer on the first address (reset / protocol error) falls back."""
    payload = _zip_bytes({"SKILL.md": "---\nname: demo\n---\n"})
    good = skillhub_net.tls_server(_zip_handler(payload, []))
    not_tls = skillhub_net.plain_server(_zip_handler(b"", []))
    _install_test_network(
        monkeypatch,
        skillhub_net,
        {
            "api.skillhub.test": [
                ("127.0.0.1", not_tls.port),
                ("127.0.0.1", good.port),
            ]
        },
    )

    files = skillhub_market.download_skillhub_package_files(
        "demo",
        host="https://api.skillhub.test",
        timeout=5.0,
    )

    assert dict(files) == {"SKILL.md": b"---\nname: demo\n---\n"}
    assert good.sni == ["api.skillhub.test"]


def test_download_raises_timeout_when_every_address_stalls(
    monkeypatch: pytest.MonkeyPatch,
    skillhub_net: _SkillHubTestNet,
) -> None:
    _install_test_network(
        monkeypatch,
        skillhub_net,
        {
            "api.skillhub.test": [
                ("127.0.0.1", skillhub_net.stalled_address()),
                ("127.0.0.1", skillhub_net.stalled_address()),
            ]
        },
    )

    with pytest.raises(skillhub_market.SkillHubMarketTimeout):
        skillhub_market.download_skillhub_package_files(
            "demo",
            host="https://api.skillhub.test",
            timeout=0.5,
        )


def test_download_follows_redirect_and_falls_back_on_target_host(
    monkeypatch: pytest.MonkeyPatch,
    skillhub_net: _SkillHubTestNet,
) -> None:
    """The 302 hop (``download`` -> CDN) resolves its own addresses and falls back."""
    payload = _zip_bytes({"SKILL.md": "---\nname: demo\n---\n"})
    cdn = skillhub_net.tls_server(_zip_handler(payload, []))
    api = skillhub_net.tls_server(_redirect_handler("https://cdn.skillhub.test/package.zip"))
    stalled = skillhub_net.stalled_address()
    _install_test_network(
        monkeypatch,
        skillhub_net,
        {
            "api.skillhub.test": [("127.0.0.1", api.port)],
            "cdn.skillhub.test": [("127.0.0.1", stalled), ("127.0.0.1", cdn.port)],
        },
    )

    files = skillhub_market.download_skillhub_package_files(
        "demo",
        host="https://api.skillhub.test",
        timeout=1.0,
    )

    assert dict(files) == {"SKILL.md": b"---\nname: demo\n---\n"}
    assert api.sni == ["api.skillhub.test"]
    assert cdn.sni == ["cdn.skillhub.test"]
