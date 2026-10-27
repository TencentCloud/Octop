"""Portal catalog reads for the plugin and expert markets."""

from __future__ import annotations

import io
import json
import socket
import ssl
import zipfile
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

import octop.infra.market.http as market_http
from octop.infra.market import (
    PortalMarketError,
    clear_market_cache,
    get_market_expert,
    install_portal_expert,
    list_market_experts,
    list_market_plugins,
    pick_localized,
)


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _isolated_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_PORTAL_URL", "")
    clear_market_cache()


def _portal_body(items: list[dict[str, Any]]) -> bytes:
    return json.dumps({"success": True, "data": {"items": items}}).encode()


def test_portal_catalog_lists_plugins_and_experts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_PORTAL_URL", "https://octop.cloud")
    plugin = {
        "id": "weather",
        "version": "0.1.0",
        "name": {"zh": "天气", "en": "Weather"},
        "description": {"zh": "天气", "en": "Weather"},
        "download_url": (
            "https://download.octop.cloud/octop/market/plugins/weather/0.1.0/weather-0.1.0.zip"
        ),
    }
    expert = {
        "id": "ops-engineer",
        "slug": "ops-engineer",
        "version": "1.0.0",
        "label": {"zh": "运维", "en": "Ops"},
        "description": {"zh": "描述", "en": "Description"},
        "scene": "tech",
        "download_url": (
            "https://download.octop.cloud/octop/market/experts/ops-engineer/1.0.0/"
            "ops-engineer-1.0.0.zip"
        ),
    }
    calls: list[str] = []

    def fake_fetch(url: str, *, limit: int) -> bytes:
        del limit
        calls.append(url)
        if url.endswith("/api/market/plugins"):
            return _portal_body([plugin])
        if url.endswith("/api/market/experts"):
            return _portal_body([expert])
        raise PortalMarketError("not found", status=404)

    monkeypatch.setattr(market_http, "fetch_bytes", fake_fetch)

    plugins = list_market_plugins()
    assert plugins[0]["id"] == "weather"
    assert plugins[0]["download_url"].endswith("/plugins/weather/0.1.0/weather-0.1.0.zip")
    expert_row = get_market_expert("ops-engineer")
    assert expert_row is not None
    assert expert_row["slug"] == "ops-engineer"
    assert pick_localized(plugins[0]["name"], "en") == "Weather"
    items, scenes = list_market_experts(query="ops", scene="tech")
    assert [item["slug"] for item in items] == ["ops-engineer"]
    assert scenes == ["tech"]
    assert calls == [
        "https://octop.cloud/api/market/plugins",
        "https://octop.cloud/api/market/experts",
    ]
    assert all("index.json" not in url and "meta.json" not in url for url in calls)


def test_portal_failure_does_not_fetch_object_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_PORTAL_URL", "https://octop.cloud")
    calls: list[str] = []

    def fake_fetch(url: str, *, limit: int) -> bytes:
        del limit
        calls.append(url)
        raise PortalMarketError("timeout")

    monkeypatch.setattr(market_http, "fetch_bytes", fake_fetch)
    with pytest.raises(PortalMarketError, match="timeout"):
        list_market_plugins()
    assert calls == ["https://octop.cloud/api/market/plugins"]


def test_install_portal_expert_extracts_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_PORTAL_URL", "https://octop.cloud")
    package = _zip_bytes(
        {"manifest.json": json.dumps({"id": "ops-engineer", "label": {"zh": "运维", "en": "Ops"}})}
    )
    archive_url = (
        "https://download.octop.cloud/octop/market/experts/ops-engineer/1.0.0/"
        "ops-engineer-1.0.0.zip"
    )

    def fake_fetch(url: str, *, limit: int) -> bytes:
        del limit
        if url == archive_url:
            return package
        if url.endswith("/api/market/experts"):
            return _portal_body(
                [
                    {
                        "slug": "ops-engineer",
                        "label": {"zh": "运维", "en": "Ops"},
                        "icon_url": (
                            "https://download.octop.cloud/octop/market/experts/"
                            "ops-engineer/1.0.0/avatar.svg"
                        ),
                        "download_url": archive_url,
                    }
                ]
            )
        raise PortalMarketError("not found", status=404)

    monkeypatch.setattr(market_http, "fetch_bytes", fake_fetch)
    installed = install_portal_expert("ops-engineer", tmp_path)
    assert installed is not None
    assert installed.expert_id == "ops-engineer"
    manifest = json.loads((tmp_path / "ops-engineer" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "ops-engineer"


def test_market_remote_url_overrides_object_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_MARKET_REMOTE_URL", "files.example.com/ignored")
    assert market_http.remote_base() == "https://files.example.com"
    archive = "https://files.example.com/octop/market/plugins/weather/0.1.0/weather-0.1.0.zip"
    assert market_http.is_market_archive_url(archive)
    public = archive.replace("files.example.com", "download.octop.cloud")
    assert not market_http.is_market_archive_url(public)


def test_market_remote_url_keeps_explicit_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_MARKET_REMOTE_URL", "http://127.0.0.1:9000/")
    assert market_http.remote_base() == "http://127.0.0.1:9000"
    assert market_http.is_market_archive_url(
        "http://127.0.0.1:9000/octop/market/experts/ops/1.0.0/ops-1.0.0.zip"
    )
    assert not market_http.is_market_archive_url(
        "http://127.0.0.1/octop/market/experts/ops/1.0.0/ops-1.0.0.zip"
    )


def test_dns_failure_is_a_local_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> bytes:
        raise URLError(socket.gaierror(8, "nodename nor servname provided"))

    monkeypatch.setattr(market_http, "urlopen", boom)
    with pytest.raises(PortalMarketError) as raised:
        market_http.fetch_bytes("https://octop.cloud/api/market/plugins", limit=64)
    assert raised.value.network is True


def test_other_urlerror_is_not_a_local_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> bytes:
        raise URLError(ssl.SSLError("CERTIFICATE_VERIFY_FAILED"))

    monkeypatch.setattr(market_http, "urlopen", boom)
    with pytest.raises(PortalMarketError) as raised:
        market_http.fetch_bytes("https://octop.cloud/api/market/plugins", limit=64)
    assert raised.value.network is False


def test_http_catalog_error_is_a_market_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> bytes:
        raise HTTPError(
            "https://octop.cloud/api/market/plugins",
            502,
            "bad gateway",
            EmailMessage(),
            io.BytesIO(b""),
        )

    monkeypatch.setattr(market_http, "urlopen", boom)
    with pytest.raises(PortalMarketError) as raised:
        market_http.fetch_bytes("https://octop.cloud/api/market/plugins", limit=64)
    assert raised.value.network is False
    assert raised.value.status == 502


def test_empty_portal_url_does_not_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_fetch(url: str, *, limit: int) -> bytes:
        del limit
        calls.append(url)
        raise AssertionError(url)

    monkeypatch.setattr(market_http, "fetch_bytes", fake_fetch)
    with pytest.raises(PortalMarketError, match="portal url is empty"):
        list_market_plugins()
    assert calls == []
