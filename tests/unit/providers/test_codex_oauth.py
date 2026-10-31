"""Unit tests for Codex OAuth helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

import pytest

from octop.infra.agents.providers.codex_apply import CODEX_MODELS, CODEX_PROVIDER_NAME
from octop.infra.agents.providers.codex_oauth import (
    CodexOAuthCredentials,
    CodexOAuthDeviceCodeError,
    CodexOAuthRefreshError,
    build_codex_headers,
    exchange_device_code,
    get_valid_access_token,
    load_codex_token,
    poll_device_token,
    refresh_codex_token,
    request_device_code,
    save_codex_token,
)
from octop.infra.utils.paths import PathLayout


class _Resp:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_request_device_code_parses_response() -> None:
    payload = json.dumps(
        {"device_auth_id": "dev-1", "user_code": "ABCD-1234", "interval": 5}
    ).encode()

    def fake_urlopen(req: urllib.request.Request, timeout: float = 30) -> _Resp:
        assert "deviceauth/usercode" in req.full_url
        return _Resp(payload)

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        info = request_device_code()

    assert info["device_auth_id"] == "dev-1"
    assert info["user_code"] == "ABCD-1234"
    assert info["interval_s"] == 5
    assert urlparse(info["verification_url"]).hostname == "auth.openai.com"


def test_request_device_code_normalizes_network_failures() -> None:
    def fake_urlopen(req: urllib.request.Request, timeout: float = 30) -> _Resp:
        raise urllib.error.URLError("DNS lookup failed")

    with (
        mock.patch("urllib.request.urlopen", fake_urlopen),
        pytest.raises(CodexOAuthDeviceCodeError) as raised,
    ):
        request_device_code()

    assert raised.value.reason == "network_error"
    assert raised.value.upstream_status is None
    assert "DNS lookup failed" not in str(raised.value)


def test_request_device_code_preserves_upstream_http_status() -> None:
    def fake_urlopen(req: urllib.request.Request, timeout: float = 30) -> _Resp:
        raise urllib.error.HTTPError(req.full_url, 503, "unavailable", {}, None)  # type: ignore[arg-type]

    with (
        mock.patch("urllib.request.urlopen", fake_urlopen),
        pytest.raises(CodexOAuthDeviceCodeError) as raised,
    ):
        request_device_code()

    assert raised.value.reason == "upstream_http_error"
    assert raised.value.upstream_status == 503


def test_poll_device_token_returns_none_while_pending() -> None:
    def fake_urlopen(req: urllib.request.Request, timeout: float = 30) -> _Resp:
        raise urllib.error.HTTPError(req.full_url, 403, "pending", {}, None)  # type: ignore[arg-type]

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        result = poll_device_token("dev-1", "ABCD-1234")

    assert result is None


def test_poll_device_token_returns_code_on_success() -> None:
    payload = json.dumps({"authorization_code": "auth-code", "code_verifier": "verifier"}).encode()

    def fake_urlopen(req: urllib.request.Request, timeout: float = 30) -> _Resp:
        assert "deviceauth/token" in req.full_url
        return _Resp(payload)

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        result = poll_device_token("dev-1", "ABCD-1234")

    assert result == ("auth-code", "verifier")


def test_exchange_device_code_builds_credentials() -> None:
    payload = json.dumps(
        {"access_token": "access-tok", "refresh_token": "refresh-tok", "expires_in": 3600}
    ).encode()

    def fake_urlopen(req: urllib.request.Request, timeout: float = 30) -> _Resp:
        assert req.full_url.endswith("/oauth/token")
        return _Resp(payload)

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        cred = exchange_device_code("auth-code", "verifier")

    assert cred["access"] == "access-tok"
    assert cred["refresh"] == "refresh-tok"


def test_build_codex_headers_includes_account_id() -> None:
    headers = build_codex_headers("acct-123")
    assert headers["originator"] == "openclaw"
    assert headers["chatgpt-account-id"] == "acct-123"
    assert "User-Agent" in headers


def test_codex_provider_constants() -> None:
    assert CODEX_PROVIDER_NAME == "openai-codex"
    assert any(m["id"] == "gpt-5.4" for m in CODEX_MODELS)


def _expired_cred() -> CodexOAuthCredentials:
    return CodexOAuthCredentials(
        access="old-access", refresh="old-refresh", expires=1, account_id="acct-1"
    )


def _raising_urlopen(exc: Exception) -> object:
    def fake_urlopen(req: urllib.request.Request, timeout: float = 30) -> _Resp:
        raise exc

    return fake_urlopen


def test_refresh_normalizes_network_failure(tmp_path: Path) -> None:
    with (
        mock.patch(
            "urllib.request.urlopen",
            _raising_urlopen(urllib.error.URLError("connection refused")),
        ),
        pytest.raises(CodexOAuthRefreshError) as raised,
    ):
        refresh_codex_token(PathLayout(tmp_path), _expired_cred())

    assert raised.value.reason == "network_error"


def test_refresh_rejects_body_without_access_token(tmp_path: Path) -> None:
    def fake_urlopen(req: urllib.request.Request, timeout: float = 30) -> _Resp:
        return _Resp(b'{"expires_in": 3600}')

    with (
        mock.patch("urllib.request.urlopen", fake_urlopen),
        pytest.raises(CodexOAuthRefreshError) as raised,
    ):
        refresh_codex_token(PathLayout(tmp_path), _expired_cred())

    assert raised.value.reason == "invalid_response"


def test_get_valid_access_token_returns_none_when_refresh_network_fails(
    tmp_path: Path,
) -> None:
    layout = PathLayout(tmp_path)
    save_codex_token(layout, _expired_cred())

    with mock.patch(
        "urllib.request.urlopen", _raising_urlopen(urllib.error.URLError("dns failure"))
    ):
        assert get_valid_access_token(layout) is None

    assert load_codex_token(layout) == _expired_cred()
