"""Movie-search must ask Bangumi for the response group that carries ratings."""

from __future__ import annotations

import importlib.util
import json
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root


def _load_movie_search() -> Any:
    path = default_bundled_plugins_root() / "movie-search" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_movie_search", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SUBJECT: dict[str, Any] = {
    "id": 515759,
    "name": "葬送のフリーレン",
    "name_cn": "葬送的芙莉莲",
    "type": 2,
    "images": {"large": "https://lain.bgm.tv/pic/cover/l/0b/24/515759_qA1Zc.jpg"},
    "summary": "魔王を倒した後の旅。",
}

# Captured from api.bgm.tv on 2026-09-22; only the large group ships `rating`.
_RATING: dict[str, Any] = {"total": 12391, "count": {"10": 461}, "score": 7.5}


class _FakeResp:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    """Serves `rating` only when responseGroup asks for the large group, like bgm.tv."""

    last_params: Any = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        params = kwargs.get("params") or {}
        type(self).last_params = params
        row = dict(_SUBJECT)
        if params.get("responseGroup") == "large":
            row["rating"] = _RATING
        return _FakeResp({"results": 1, "list": [row]})


async def test_search_movie_surfaces_the_bangumi_rating(monkeypatch: Any) -> None:
    mod = _load_movie_search()
    monkeypatch.setattr(mod.httpx, "Client", _FakeClient)
    payload = json.loads(await mod.search_movie("葬送的芙莉莲", limit=5))

    assert payload["data"]["items"][0]["score"] == 7.5
    assert "7.5" in payload["text"]
