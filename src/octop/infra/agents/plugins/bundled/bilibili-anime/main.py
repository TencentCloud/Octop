"""Bilibili anime search + episode list for chat UI player.

Uses public Bilibili HTTP APIs from the Octop server (avoids browser CORS).
Playback in the Dashboard uses the official iframe player.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from harness_agent.plugins import PluginContext

logger = logging.getLogger("octop.plugins.bilibili_anime")

_TAG_RE = re.compile(r"<[^>]+>")
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
}


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


def _client() -> httpx.Client:
    return httpx.Client(timeout=25.0, headers=_HEADERS, follow_redirects=True)


def _search_bangumi(keyword: str, *, page: int = 1) -> list[dict[str, Any]]:
    with _client() as client:
        # wbi endpoint is less likely to return -412 than the legacy search URL
        resp = client.get(
            "https://api.bilibili.com/x/web-interface/wbi/search/type",
            params={
                "search_type": "media_bangumi",
                "keyword": keyword,
                "page": page,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
    if int(payload.get("code") or 0) != 0:
        raise RuntimeError(payload.get("message") or f"search failed: {payload.get('code')}")
    raw_list = (payload.get("data") or {}).get("result") or []
    out: list[dict[str, Any]] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        season_id = item.get("season_id")
        if season_id is None:
            continue
        out.append(
            {
                "season_id": int(season_id),
                "media_id": int(item["media_id"]) if item.get("media_id") is not None else None,
                "title": _strip_html(str(item.get("title") or "")),
                "cover": str(item.get("cover") or ""),
                "styles": str(item.get("styles") or ""),
                "areas": str(item.get("areas") or ""),
                "index_show": str(item.get("index_show") or ""),
                "season_type_name": str(item.get("season_type_name") or "番剧"),
                "desc": _strip_html(str(item.get("desc") or item.get("evaluate") or "")),
                "url": str(
                    item.get("goto_url") or f"https://www.bilibili.com/bangumi/play/ss{season_id}"
                ),
                "episodes": [],
            },
        )
    return out


def _fetch_episodes(season_id: int) -> list[dict[str, Any]]:
    with _client() as client:
        resp = client.get(
            "https://api.bilibili.com/pgc/view/web/season",
            params={"season_id": season_id},
        )
        resp.raise_for_status()
        payload = resp.json()
    if int(payload.get("code") or 0) != 0:
        raise RuntimeError(payload.get("message") or f"season failed: {payload.get('code')}")
    result = payload.get("result") or payload.get("data") or {}
    episodes_raw = list(result.get("episodes") or [])
    # Include positive/main section episodes only; skip PV sections for nav clarity
    for section in result.get("section") or []:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "")
        if "PV" in title.upper() or "预告" in title:
            continue
        for ep in section.get("episodes") or []:
            if isinstance(ep, dict):
                episodes_raw.append(ep)

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for idx, ep in enumerate(episodes_raw, start=1):
        if not isinstance(ep, dict):
            continue
        bvid = str(ep.get("bvid") or "").strip()
        if not bvid:
            continue
        key = bvid
        if key in seen:
            continue
        seen.add(key)
        title = str(ep.get("title") or idx)
        long_title = str(ep.get("long_title") or "").strip()
        label = f"第{title}话" if title.isdigit() else title
        if long_title:
            label = f"{label} {long_title}".strip()
        out.append(
            {
                "index": len(out) + 1,
                "ep_id": ep.get("id"),
                "title": title,
                "long_title": long_title,
                "label": label,
                "bvid": bvid,
                "aid": ep.get("aid"),
                "cid": ep.get("cid"),
                "badge": str(ep.get("badge") or ""),
            },
        )
    return out


async def bilibili_search_anime(keyword: str, max_seasons: int = 5) -> str:
    """Search Bilibili bangumi (anime) by keyword and return playable episode lists.

    The Dashboard renders an in-chat player with season switching and episode
    navigation (official Bilibili iframe player).
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return json.dumps(
            {
                "octop_ui": {"renderer": "bilibili_player", "version": 1},
                "data": {"keyword": "", "results": [], "error": "keyword is required"},
                "text": "请提供要搜索的番剧名称。",
            },
            ensure_ascii=False,
        )

    try:
        results = _search_bangumi(keyword)
    except Exception as exc:
        logger.exception("bilibili search failed")
        return json.dumps(
            {
                "octop_ui": {"renderer": "bilibili_player", "version": 1},
                "data": {"keyword": keyword, "results": [], "error": str(exc)},
                "text": f"搜索失败：{exc}",
            },
            ensure_ascii=False,
        )

    limit = max(1, min(int(max_seasons or 5), 8))
    for item in results[:limit]:
        try:
            item["episodes"] = _fetch_episodes(int(item["season_id"]))
        except Exception as exc:
            logger.warning("season %s episodes failed: %s", item.get("season_id"), exc)
            item["episodes"] = []
            item["episodes_error"] = str(exc)

    selected = results[0]["season_id"] if results else None
    text = (
        f"找到 {len(results)} 部与「{keyword}」相关的番剧。"
        if results
        else f"未找到与「{keyword}」相关的番剧。"
    )
    if results and results[0].get("episodes"):
        text += f" 默认选中《{results[0]['title']}》，共 {len(results[0]['episodes'])} 集。"

    payload = {
        "octop_ui": {"renderer": "bilibili_player", "version": 1},
        "data": {
            "keyword": keyword,
            "results": results[:limit],
            "selected_season_id": selected,
            "current_episode": 1,
        },
        "text": text,
    }
    return json.dumps(payload, ensure_ascii=False)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "bilibili_search_anime",
        bilibili_search_anime,
        description=(
            "在哔哩哔哩搜索番剧/动漫，并在聊天中渲染可播放的分集播放器。"
            "参数 keyword 为番剧名（如「葬送的芙莉莲」「进击的巨人」）。"
        ),
    )
