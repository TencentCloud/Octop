"""Bilibili anime search must stay small enough for the in-chat player."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root

# deepagents 0.7.9 evicts tool results above 4 * 20_000 characters.
_EVICTION_CHARS = 80_000


def _load_plugin():
    path = default_bundled_plugins_root() / "bilibili-anime" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_bilibili_anime", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _episode(index: int) -> dict[str, Any]:
    return {
        "index": index,
        "ep_id": 700000 + index,
        "title": str(index),
        "long_title": f"凡人风起天南{index}重制版",
        "label": f"第{index}话 凡人风起天南{index}重制版",
        "bvid": f"BV1vT4{index:06d}",
        "aid": 400000000 + index,
        "cid": 1000000000 + index,
        "badge": "",
    }


def _season(season_id: int, *, episodes: int) -> dict[str, Any]:
    return {
        "season_id": season_id,
        "media_id": season_id,
        "title": f"凡人修仙传{season_id}",
        "cover": "https://i0.hdslb.com/bfs/bangumi/image/" + "a" * 64 + ".png",
        "styles": "小说改/玄幻/热血/励志",
        "areas": "中国大陆",
        "index_show": f"更新至第{episodes}话",
        "season_type_name": "国创",
        "desc": "看机智的凡人小子韩立如何稳健发展、步步为营。" * 8,
        "url": f"https://www.bilibili.com/bangumi/play/ss{season_id}",
        "episodes": [_episode(i) for i in range(1, episodes + 1)],
    }


def _install(mod: Any, monkeypatch: Any, seasons: list[dict[str, Any]]) -> list[int]:
    fetched: list[int] = []

    def search(_keyword: str, *, page: int = 1) -> list[dict[str, Any]]:
        del page
        return [{**item, "episodes": []} for item in seasons]

    def fetch(season_id: int) -> list[dict[str, Any]]:
        fetched.append(season_id)
        match = next(item for item in seasons if item["season_id"] == season_id)
        return list(match["episodes"])

    monkeypatch.setattr(mod, "_search_bangumi", search)
    monkeypatch.setattr(mod, "_fetch_episodes", fetch)
    return fetched


def test_long_series_stays_inline_and_keeps_the_top_season(monkeypatch: Any) -> None:
    mod = _load_plugin()
    seasons = [_season(season_id, episodes=400) for season_id in (28747, 28748, 28749, 28750)]
    fetched = _install(mod, monkeypatch, seasons)

    payload_text = asyncio.run(mod.bilibili_search_anime("凡人修仙传"))
    payload = json.loads(payload_text)
    results = payload["data"]["results"]

    assert len(payload_text) <= mod._MAX_RESULT_CHARS
    assert len(payload_text) < _EVICTION_CHARS
    assert results[0]["season_id"] == 28747
    assert len(results[0]["episodes"]) == 400
    assert "episodes_truncated" not in results[0]
    assert results[0]["episodes"][0]["bvid"].startswith("BV")
    assert "aid" in results[0]["episodes"][0]
    assert "cid" in results[0]["episodes"][0]
    assert "ep_id" not in results[0]["episodes"][0]
    assert "cover" not in results[0]
    assert all(item["season_id"] == 28747 for item in results)
    assert "未展开分集" in payload["text"]
    assert "凡人修仙传28748" in payload["text"]
    assert fetched == [28747, 28748]


def test_short_search_returns_every_requested_season(monkeypatch: Any) -> None:
    mod = _load_plugin()
    seasons = [_season(1, episodes=3), _season(2, episodes=2)]
    fetched = _install(mod, monkeypatch, seasons)

    payload = json.loads(asyncio.run(mod.bilibili_search_anime("葬送的芙莉莲", max_seasons=5)))

    assert [item["season_id"] for item in payload["data"]["results"]] == [1, 2]
    assert payload["data"]["selected_season_id"] == 1
    assert payload["data"]["results"][0]["episodes"][0]["label"].startswith("第1话")
    assert "共 3 集" in payload["text"]
    assert "另有 1 部可在播放器中切换" in payload["text"]
    assert "未展开分集" not in payload["text"]
    assert fetched == [1, 2]


def test_single_huge_season_is_truncated_instead_of_evicted(monkeypatch: Any) -> None:
    mod = _load_plugin()
    seasons = [_season(9, episodes=3000)]
    _install(mod, monkeypatch, seasons)

    payload_text = asyncio.run(mod.bilibili_search_anime("超长番"))
    payload = json.loads(payload_text)
    season = payload["data"]["results"][0]

    assert len(payload_text) <= mod._MAX_RESULT_CHARS
    assert season["episodes_truncated"] is True
    assert season["episode_total"] == 3000
    assert 0 < len(season["episodes"]) < 3000
    assert "播放器先载入前" in payload["text"]
    assert "共 3000 集" in payload["text"]


def test_empty_keyword_does_not_search(monkeypatch: Any) -> None:
    mod = _load_plugin()

    def explode(_keyword: str, *, page: int = 1) -> list[dict[str, Any]]:
        del page
        raise AssertionError("search should not run")

    monkeypatch.setattr(mod, "_search_bangumi", explode)

    payload = json.loads(asyncio.run(mod.bilibili_search_anime("  ")))
    assert payload["data"]["results"] == []
    assert payload["data"]["error"] == "keyword is required"
