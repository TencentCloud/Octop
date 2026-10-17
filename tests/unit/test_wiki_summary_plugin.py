"""Wiki-summary plugin must keep every request under ``*.wikipedia.org``."""

from __future__ import annotations

import importlib.util
import json
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root


def _load_wiki_summary() -> Any:
    path = default_bundled_plugins_root() / "wiki-summary" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_wiki_summary", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeResp:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> Any:
        return self._payload


class _RecordingClient:
    urls: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> _RecordingClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        type(self).urls.append(url)
        if "/api/rest_v1/page/summary/" in url:
            return _FakeResp({"title": "地球", "extract": "太阳系第三行星。"})
        return _FakeResp({})


def _data(payload: str) -> dict[str, Any]:
    return json.loads(payload)["data"]


async def test_plain_lang_hits_the_wikipedia_subdomain(monkeypatch: Any) -> None:
    mod = _load_wiki_summary()
    _RecordingClient.urls = []
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    out = await mod.wiki_summary("Earth", lang="en")
    assert _RecordingClient.urls == ["https://en.wikipedia.org/api/rest_v1/page/summary/Earth"]
    assert _data(out)["extract"] == "太阳系第三行星。"


async def test_hyphenated_and_simple_lang_codes_still_resolve(monkeypatch: Any) -> None:
    mod = _load_wiki_summary()
    _RecordingClient.urls = []
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    for lang in ("zh-classical", "simple", "NB"):
        await mod.wiki_summary("Earth", lang=lang)
    assert [u.split("/api/")[0] for u in _RecordingClient.urls] == [
        "https://zh-classical.wikipedia.org",
        "https://simple.wikipedia.org",
        "https://nb.wikipedia.org",
    ]


async def test_lang_cannot_retarget_the_host(monkeypatch: Any) -> None:
    """``lang`` is interpolated into the URL host, so it must not carry URL syntax.

    The tool schema gives the model a free-form ``str``, so a value like
    ``evil.com#`` would otherwise send a request to an arbitrary host and echo
    its JSON body back into the chat.
    """
    mod = _load_wiki_summary()
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    for raw in (
        "evil.com#",
        "localhost:8443/",
        "en.wikipedia.org.evil.cn",
        "x/..",
        "../../etc/passwd",
        "zh.wikipedia.org#x",
    ):
        _RecordingClient.urls = []
        out = await mod.wiki_summary("Earth", lang=raw)
        assert _RecordingClient.urls == [], raw
        assert _data(out).get("error") == "invalid lang", raw
