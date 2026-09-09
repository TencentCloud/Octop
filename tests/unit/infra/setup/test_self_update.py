"""Tests for octop.infra.setup.self_update."""

from __future__ import annotations

import json
import urllib.error

import pytest

from octop.infra.setup import self_update
from octop.infra.setup.self_update import is_newer, parse_version


def test_parse_version_ignores_suffix() -> None:
    assert parse_version("0.7.2") > parse_version("0.7.1")
    assert parse_version("0.7.1rc1") == parse_version("0.7.1")


def test_is_newer() -> None:
    assert is_newer("0.7.2", "0.7.1")
    assert not is_newer("0.7.1", "0.7.2")
    assert not is_newer("0.7.1", "0.7.1")


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def _json_body(version: str) -> bytes:
    return json.dumps(
        {"info": {"version": version, "description": "## [Changelog]\n\n- entry"}}
    ).encode()


@pytest.fixture()
def _no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(self_update.time, "sleep", lambda _: None)


def test_fetch_pypi_info_returns_official_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_urlopen(req: urllib.request.Request, timeout: int = 0) -> _FakeResponse:
        calls.append(req.full_url)
        return _FakeResponse(_json_body("1.2.3"))

    monkeypatch.setattr(self_update.urllib.request, "urlopen", fake_urlopen)

    info = self_update.fetch_pypi_info()

    assert info is not None
    assert info.version == "1.2.3"
    assert info.source == "pypi.org"
    assert calls[0].startswith("https://pypi.org/")


def test_fetch_pypi_info_retries_pypi_then_falls_back_to_mirror(
    monkeypatch: pytest.MonkeyPatch, _no_retry_delay: None
) -> None:
    calls: list[str] = []

    def fake_urlopen(req: urllib.request.Request, timeout: int = 0) -> _FakeResponse:
        url = req.full_url
        calls.append(url)
        if url.startswith("https://pypi.org/"):
            raise urllib.error.URLError("connection reset")
        return _FakeResponse(_json_body("1.2.4"))

    monkeypatch.setattr(self_update.urllib.request, "urlopen", fake_urlopen)

    info = self_update.fetch_pypi_info()

    assert info is not None
    assert info.version == "1.2.4"
    assert info.source == "mirrors.cloud.tencent.com"
    assert calls.count(self_update._PYPI_URL) == 2


def test_fetch_pypi_info_skips_malformed_payload(
    monkeypatch: pytest.MonkeyPatch, _no_retry_delay: None
) -> None:
    def fake_urlopen(req: urllib.request.Request, timeout: int = 0) -> _FakeResponse:
        url = req.full_url
        if url.startswith("https://pypi.org/"):
            return _FakeResponse(b"{not json")
        return _FakeResponse(_json_body("2.0.0"))

    monkeypatch.setattr(self_update.urllib.request, "urlopen", fake_urlopen)

    info = self_update.fetch_pypi_info()

    assert info is not None
    assert info.version == "2.0.0"


def test_fetch_pypi_info_returns_none_when_all_sources_fail(
    monkeypatch: pytest.MonkeyPatch, _no_retry_delay: None
) -> None:
    def fake_urlopen(req: urllib.request.Request, timeout: int = 0) -> _FakeResponse:
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(self_update.urllib.request, "urlopen", fake_urlopen)

    assert self_update.fetch_pypi_info() is None
