"""Air-quality plugin must label a coordinate lookup by its coordinates."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root

_CURRENT = {"pm2_5": 11.2, "pm10": 18.0, "us_aqi": 41, "european_aqi": 22}
_TOKYO = (35.6895, 139.6917)


def _load_air_quality():
    path = default_bundled_plugins_root() / "air-quality" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_air_quality", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeResp:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _RecordingClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.geo_names: list[str] = []

    def __enter__(self) -> _RecordingClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        params = dict(kwargs.get("params") or {})
        if "geocoding-api.open-meteo.com" in url:
            self.geo_names.append(str(params.get("name")))
            return _FakeResp(
                {
                    "results": [
                        {"name": "北京", "country": "中国", "latitude": 39.9, "longitude": 116.4}
                    ]
                }
            )
        return _FakeResp({"current": _CURRENT})


def _envelope(output: str) -> dict[str, Any]:
    return json.loads(output)


def _query(monkeypatch: Any, **kwargs: Any) -> tuple[dict[str, Any], _RecordingClient]:
    mod = _load_air_quality()
    holder: dict[str, _RecordingClient] = {}

    def _client(*args: Any, **client_kwargs: Any) -> _RecordingClient:
        holder["client"] = _RecordingClient(*args, **client_kwargs)
        return holder["client"]

    monkeypatch.setattr(mod.httpx, "Client", _client)
    envelope = _envelope(asyncio.run(mod.get_air_quality(**kwargs)))
    return envelope, holder["client"]


def test_coordinates_without_city_are_not_labelled_beijing(monkeypatch: Any) -> None:
    envelope, client = _query(monkeypatch, lat=_TOKYO[0], lon=_TOKYO[1])
    data = envelope["data"]

    assert data["latitude"] == _TOKYO[0]
    assert data["city"] == "35.6895,139.6917"
    assert "Beijing" not in envelope["text"]
    assert client.geo_names == []  # coordinates need no geocoding round-trip


def test_city_name_with_coordinates_stays_the_label(monkeypatch: Any) -> None:
    envelope, _ = _query(monkeypatch, city="Tokyo", lat=_TOKYO[0], lon=_TOKYO[1])

    assert envelope["data"]["city"] == "Tokyo"


def test_city_only_still_geocodes_that_city(monkeypatch: Any) -> None:
    envelope, client = _query(monkeypatch, city="Chengdu")
    data = envelope["data"]

    assert client.geo_names == ["Chengdu"]
    assert data["city"] == "北京, 中国"
    assert data["latitude"] == 39.9


def test_no_arguments_still_default_to_beijing(monkeypatch: Any) -> None:
    envelope, client = _query(monkeypatch)

    assert client.geo_names == ["Beijing"]
    assert envelope["data"]["city"] == "北京, 中国"
