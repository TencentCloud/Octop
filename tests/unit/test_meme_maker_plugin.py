"""Meme-maker plugin must escape text so it stays inside its own URL segment."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root


def _load_meme_maker():  # type: ignore[no-untyped-def]
    path = default_bundled_plugins_root() / "meme-maker" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_meme_maker", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeResp:
    status_code = 200


class _RecordingClient:
    last_urls: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> _RecordingClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def head(self, url: str, **kwargs: Any) -> _FakeResp:
        type(self).last_urls.append(url)
        return _FakeResp()

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        type(self).last_urls.append(url)
        return _FakeResp()


def _make(monkeypatch, **kwargs: Any) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    mod = _load_meme_maker()
    _RecordingClient.last_urls = []
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    payload = json.loads(asyncio.run(mod.make_meme(**kwargs)))
    assert isinstance(payload["data"], dict)
    return payload


def test_slash_is_escaped_into_its_segment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    result = _make(monkeypatch, template="doge", top="to/be", bottom="")

    assert result["data"]["image_url"].endswith("/images/doge/to~sbe/_.png")
    assert _RecordingClient.last_urls[0] == result["data"]["image_url"]


def test_slash_does_not_shift_the_bottom_caption(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    result = _make(monkeypatch, template="doge", top="yes/no", bottom="maybe/so")

    path = result["data"]["image_url"].split("/images/")[1]
    assert path == "doge/yes~sno/maybe~sso.png"
    assert result["data"]["bottom"] == "maybe/so"


def test_documented_escapes_round_trip(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mod = _load_meme_maker()

    assert mod._encode_segment("a-b_c?d&e#f%g/h") == "a--b__c~qd~ae~hf~pg~sh"
