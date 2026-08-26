"""Hot-topics plugin must use unauthenticated public endpoints."""

from __future__ import annotations

import importlib.util
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root


def _load_hot_topics():
    path = default_bundled_plugins_root() / "hot-topics" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_hot_topics", path)
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
    last_url = ""
    last_headers: dict[str, str] = {}
    last_params: Any = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.headers = dict(kwargs.get("headers") or {})

    def __enter__(self) -> _RecordingClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        type(self).last_url = url
        type(self).last_headers = dict(self.headers)
        type(self).last_params = kwargs.get("params")
        if "weibo.com/ajax/side/hotSearch" in url:
            return _FakeResp(
                {"data": {"realtime": [{"note": "测试热搜", "word": "测试热搜", "num": "1"}]}},
            )
        if "api.zhihu.com/topstory/hot-list" in url:
            return _FakeResp(
                {
                    "data": [
                        {
                            "detail_text": "100 万热度",
                            "target": {
                                "id": 123,
                                "title": "测试知乎",
                                "url": "https://api.zhihu.com/questions/123",
                            },
                        },
                    ],
                },
            )
        return _FakeResp({}, status=401)


def test_weibo_sends_referer(monkeypatch: Any) -> None:
    mod = _load_hot_topics()
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    items = mod._weibo(5)
    assert "weibo.com/ajax/side/hotSearch" in _RecordingClient.last_url
    assert _RecordingClient.last_headers.get("Referer", "").startswith("https://weibo.com")
    assert items[0]["title"] == "测试热搜"


def test_zhihu_uses_public_hot_list(monkeypatch: Any) -> None:
    mod = _load_hot_topics()
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    items = mod._zhihu(5)
    assert "api.zhihu.com/topstory/hot-list" in _RecordingClient.last_url
    assert "zhihu.com/api/v3/" not in _RecordingClient.last_url
    assert items[0]["title"] == "测试知乎"
    assert items[0]["url"] == "https://www.zhihu.com/question/123"
    assert "100 万热度" in items[0]["extra"]
