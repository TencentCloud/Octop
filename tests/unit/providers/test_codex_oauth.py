"""Unit tests for Codex OAuth helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from unittest import mock

from octop.infra.providers.codex_apply import CODEX_MODELS, CODEX_PROVIDER_NAME
from octop.infra.providers.codex_oauth import (
    build_codex_headers,
    exchange_device_code,
    poll_device_token,
    request_device_code,
)


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
    assert "auth.openai.com" in info["verification_url"]


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
