"""WebDAV remote backup provider unit tests (httpx MockTransport)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from octop.infra.backup.remote import get_provider
from octop.infra.backup.remote.providers import webdav as webdav_mod
from octop.infra.backup.remote.providers.webdav import WebDavBackupProvider
from octop.infra.errors import ErrorCode, OctopError


def test_from_settings_rejects_userinfo_in_url() -> None:
    with pytest.raises(OctopError) as exc_info:
        WebDavBackupProvider.from_settings(
            url="https://user:pass@dav.example/backups",
            username="u",
            password="p",
            base_dir="octop",
            verify_ssl=True,
            allow_insecure=False,
        )
    assert exc_info.value.code == ErrorCode.SLASH_BAD_ARGS
    assert "userinfo" in str(exc_info.value).lower()


def test_from_settings_rejects_http_without_allow_insecure() -> None:
    with pytest.raises(OctopError) as exc_info:
        WebDavBackupProvider.from_settings(
            url="http://dav.example/backups",
            username="u",
            password="p",
            base_dir="octop",
            verify_ssl=True,
            allow_insecure=False,
        )
    assert exc_info.value.code == ErrorCode.SLASH_BAD_ARGS
    assert "http" in str(exc_info.value).lower()


def test_webdav_registered_in_registry() -> None:
    provider = get_provider(
        "webdav",
        url="https://dav.example/backups",
        username="u",
        password="p",
        base_dir="octop",
        verify_ssl=True,
        allow_insecure=False,
    )
    assert isinstance(provider, WebDavBackupProvider)


@pytest.mark.asyncio
async def test_put_200_with_matching_head_is_remote_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = tmp_path / "octop-auto-backup-20260101T000000Z.tar.gz"
    local.write_bytes(b"abc123")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.method == "PUT":
            return httpx.Response(200)
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Content-Length": "6", "ETag": '"abc"'})
        return httpx.Response(404)

    provider = WebDavBackupProvider.from_settings(
        url="https://dav.example/backups",
        username="u",
        password="p",
        base_dir="octop",
        verify_ssl=True,
        allow_insecure=False,
        recheck_delay_s=0.0,
    )
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    result = await provider.put(local, local.name)
    assert result.status == "remote_ok"
    assert any(s.startswith("PUT ") for s in seen)
    assert any(s.startswith("HEAD ") for s in seen)


@pytest.mark.asyncio
async def test_put_201_size_echo_without_etag_is_unverified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = tmp_path / "octop-auto-backup-20260101T000000Z.tar.gz"
    local.write_bytes(b"abcdefgh")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(201)
        if request.method == "HEAD":
            # CloudDrive2-class: size already matches, no ETag completion signal.
            return httpx.Response(200, headers={"Content-Length": "8"})
        return httpx.Response(404)

    provider = WebDavBackupProvider.from_settings(
        url="https://dav.example/backups",
        username="u",
        password="secret-token",
        base_dir="octop",
        verify_ssl=True,
        allow_insecure=False,
        recheck_delay_s=0.0,
    )
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    result = await provider.put(local, local.name)
    assert result.status == "unverified"
    assert "secret-token" not in result.reason


@pytest.mark.asyncio
async def test_put_head_size_mismatch_is_remote_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = tmp_path / "octop-backup.tar.gz"
    local.write_bytes(b"abcdefgh")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(200)
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Content-Length": "1"})
        return httpx.Response(404)

    provider = WebDavBackupProvider.from_settings(
        url="https://dav.example/backups",
        username="u",
        password="p",
        base_dir="",
        verify_ssl=True,
        allow_insecure=False,
        recheck_delay_s=0.0,
    )
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    result = await provider.put(local, local.name)
    assert result.status == "remote_failed"


@pytest.mark.asyncio
async def test_error_reason_redacts_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = tmp_path / "octop-backup.tar.gz"
    local.write_bytes(b"x")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "failed to connect to https://u:super-secret@dav.example/backups/x"
        )

    provider = WebDavBackupProvider.from_settings(
        url="https://dav.example/backups",
        username="u",
        password="super-secret",
        base_dir="",
        verify_ssl=True,
        allow_insecure=False,
        recheck_delay_s=0.0,
    )
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    result = await provider.put(local, local.name)
    assert result.status == "remote_failed"
    assert "super-secret" not in result.reason


def test_redact_secrets_helper() -> None:
    text = "Authorization: Basic abcdef; password=super-secret https://u:super-secret@h/x"
    cleaned = webdav_mod.redact_secrets(text, password="super-secret")
    assert "super-secret" not in cleaned
    assert "abcdef" not in cleaned
    assert "***" in cleaned
