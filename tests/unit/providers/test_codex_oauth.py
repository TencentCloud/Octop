"""Unit tests for Codex OAuth helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from unittest import mock
from urllib.parse import urlparse

import pytest

from octop.infra.agents.providers.codex_apply import CODEX_MODELS, CODEX_PROVIDER_NAME
from octop.infra.agents.providers.codex_oauth import (
    CodexOAuthDeviceCodeError,
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


# ── N 批：原子写（`N-1`/`N-2`）与刷新单飞（`N-3`）─────────────────────────────
import os  # noqa: E402
import stat  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

from octop.infra.agents.providers.codex_oauth import (  # noqa: E402
    cleanup_stale_tmp,
    get_valid_access_token,
    load_codex_token,
    oauth_token_file,
    save_codex_token,
)
from octop.infra.utils.paths import PathLayout  # noqa: E402

posix_only = pytest.mark.skipif(os.name != "posix", reason="file mode bits are POSIX-only")


def _layout(tmp_path: Path) -> PathLayout:
    return PathLayout(root=tmp_path)


def _cred(access: str, refresh: str = "DUMMY-refresh-0001", expires: int = 0) -> dict:
    return {"access": access, "refresh": refresh, "expires": expires, "account_id": "acct-1"}


def test_save_is_atomic_and_writes_only_the_target(tmp_path: Path) -> None:
    """★ `N-1`：写完后【无 tmp 残留】∧ 内容可解析（原子性 = tmp + replace）。"""
    paths = _layout(tmp_path)
    save_codex_token(paths, _cred("DUMMY-access-0001"))  # type: ignore[arg-type]
    token_file = oauth_token_file(paths)
    assert json.loads(token_file.read_text(encoding="utf-8"))["access"] == "DUMMY-access-0001"
    assert list(tmp_path.glob(".codex_oauth.json.*.tmp")) == []


@posix_only
def test_saved_token_file_is_0600(tmp_path: Path) -> None:
    """★ `N-1`：目标文件（含 refresh token）权限 = **0600**（新建也不得 0644）。"""
    paths = _layout(tmp_path)
    save_codex_token(paths, _cred("DUMMY-access-0002"))  # type: ignore[arg-type]
    mode = stat.S_IMODE(oauth_token_file(paths).stat().st_mode)
    assert mode == 0o600, oct(mode)


@posix_only
def test_save_tightens_a_preexisting_loose_file(tmp_path: Path) -> None:
    """★ 目标已存在且是 0644 ⇒ 写入后必须收紧到 0600（不得沿用宽松权限）。"""
    paths = _layout(tmp_path)
    token_file = oauth_token_file(paths)
    token_file.write_text(json.dumps(_cred("DUMMY-old-0003")), encoding="utf-8")
    os.chmod(token_file, 0o644)
    save_codex_token(paths, _cred("DUMMY-access-0003"))  # type: ignore[arg-type]
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600


def test_interrupted_write_keeps_old_file_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ `N-1`：注入中断（`os.replace` 抛错）⇒ **旧文件仍可读**（不得被截断）∧ 无 tmp 残留。"""
    paths = _layout(tmp_path)
    save_codex_token(paths, _cred("DUMMY-old-0004"))  # type: ignore[arg-type]

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(KeyboardInterrupt):
        save_codex_token(paths, _cred("DUMMY-new-0004"))  # type: ignore[arg-type]
    monkeypatch.undo()

    cred = load_codex_token(paths)
    assert cred is not None and cred["access"] == "DUMMY-old-0004"
    assert list(tmp_path.glob(".codex_oauth.json.*.tmp")) == []


def test_stale_tmp_is_cleaned_up(tmp_path: Path) -> None:
    """★ `N-2`：陈旧的 `.{name}.*.tmp` 在下次写入前被清掉（幂等）。"""
    paths = _layout(tmp_path)
    stale = tmp_path / ".codex_oauth.json.deadbeef.tmp"
    stale.write_text("{ truncated", encoding="utf-8")
    cleanup_stale_tmp(oauth_token_file(paths))
    assert not stale.exists()
    stale.write_text("{ truncated", encoding="utf-8")
    save_codex_token(paths, _cred("DUMMY-access-0005"))  # type: ignore[arg-type]
    assert not stale.exists()


def test_refresh_is_single_flight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """★ `N-3`：并发首调只发**一次** refresh（否则后到者用被轮换的 refresh_token 会失败）。"""
    paths = _layout(tmp_path)
    save_codex_token(paths, _cred("DUMMY-expired-0006", expires=1))  # type: ignore[arg-type]
    calls: list[int] = []

    def _fake_refresh(_paths: object, cred: dict) -> dict:
        calls.append(1)
        time.sleep(0.05)  # ★ 放大并发窗口
        fresh = _cred(
            "DUMMY-fresh-0006", refresh="DUMMY-rotated-0006", expires=time.time() * 1000 + 3_600_000
        )
        save_codex_token(paths, fresh)  # type: ignore[arg-type]
        return fresh

    monkeypatch.setattr(
        "octop.infra.agents.providers.codex_oauth.refresh_codex_token", _fake_refresh
    )
    results: list[str | None] = []
    threads = [
        threading.Thread(target=lambda: results.append(get_valid_access_token(paths)))
        for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert len(calls) == 1, calls
    assert results == ["DUMMY-fresh-0006", "DUMMY-fresh-0006"], results
