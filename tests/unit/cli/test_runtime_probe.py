"""Offline-write restart hints: probe a live ``octop run`` before warning."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from octop.cli.support import runtime_probe


@pytest.fixture()
def octop_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    return tmp_path


def _write_config(home: Path, *, bind_host: str = "127.0.0.1", port: int = 8123) -> None:
    (home / "config.json").write_text(
        json.dumps({"bind_host": bind_host, "port": port}), encoding="utf-8"
    )


def _fake_get(url: str, timeout: float) -> httpx.Response:
    assert url == "http://127.0.0.1:8123/api/health"
    return httpx.Response(200, json={"ok": True})


def test_probe_returns_base_url_when_healthy(
    octop_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(octop_home)
    monkeypatch.setattr(runtime_probe.httpx, "get", _fake_get)
    assert runtime_probe.running_server_url() == "http://127.0.0.1:8123"


def test_probe_probes_loopback_for_wildcard_bind(
    octop_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(octop_home, bind_host="0.0.0.0")

    seen: list[str] = []

    def fake_get(url: str, timeout: float) -> httpx.Response:
        seen.append(url)
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(runtime_probe.httpx, "get", fake_get)
    assert runtime_probe.running_server_url() == "http://127.0.0.1:8123"
    assert seen == ["http://127.0.0.1:8123/api/health"]


def test_probe_silent_when_nothing_listens(
    octop_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(octop_home)

    def fake_get(url: str, timeout: float) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(runtime_probe.httpx, "get", fake_get)
    assert runtime_probe.running_server_url() is None


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"ok": False}),
        httpx.Response(503, json={"ok": True}),
        httpx.Response(200, json={}),
    ],
)
def test_probe_requires_healthy_json(
    response: httpx.Response,
    octop_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_config(octop_home)

    def fake(url: str, timeout: float) -> httpx.Response:
        return response

    monkeypatch.setattr(runtime_probe.httpx, "get", fake)
    assert runtime_probe.running_server_url() is None


def test_probe_without_config_file_never_creates_one(octop_home: Path) -> None:
    assert runtime_probe.running_server_url() is None
    assert not (octop_home / "config.json").exists()


def test_probe_ignores_corrupt_config(octop_home: Path) -> None:
    (octop_home / "config.json").write_text("not json", encoding="utf-8")
    assert runtime_probe.running_server_url() is None


def test_warn_prints_localized_hint_on_stderr(
    octop_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_config(octop_home)
    monkeypatch.setattr(runtime_probe.httpx, "get", _fake_get)
    runtime_probe.warn_if_server_running()
    err = capsys.readouterr().err
    assert "octop run" in err
    assert "8123" in err
    assert capsys.readouterr().out == ""


def test_warn_silent_when_server_down(
    octop_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_config(octop_home)

    def fake_get(url: str, timeout: float) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(runtime_probe.httpx, "get", fake_get)
    runtime_probe.warn_if_server_running()
    assert capsys.readouterr().err == ""
