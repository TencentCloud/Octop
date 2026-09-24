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
# harness-agent depends on deepagents 0.7.9, which replaces a tool result with a
# filesystem stub once it exceeds 4 * 20_000 characters. The in-chat player reads
# this JSON inline, so that stub means the card never renders (#1032).
_MAX_RESULT_CHARS = 60_000
_TEXT_RESERVE_CHARS = 800
_DESC_MAX_CHARS = 120


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


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _compact_episode(episode: dict[str, Any]) -> dict[str, Any]:
    """Keep the fields the in-chat player reads; drop ids the card does not use."""
    compact: dict[str, Any] = {
        "index": episode["index"],
        "title": episode["title"],
        "label": episode["label"],
        "bvid": episode["bvid"],
    }
    if episode.get("aid") is not None:
        compact["aid"] = episode["aid"]
    if episode.get("cid") is not None:
        compact["cid"] = episode["cid"]
    return compact


def _season_card(item: dict[str, Any], episodes: list[dict[str, Any]]) -> dict[str, Any]:
    card: dict[str, Any] = {
        "season_id": item["season_id"],
        "title": item.get("title") or "",
        "url": item.get("url") or "",
        "episodes": episodes,
    }
    index_show = str(item.get("index_show") or "").strip()
    if index_show:
        card["index_show"] = index_show
    desc = _clip(str(item.get("desc") or ""), _DESC_MAX_CHARS)
    if desc:
        card["desc"] = desc
    return card


def _payload_chars(keyword: str, seasons: list[dict[str, Any]]) -> int:
    payload = {
        "octop_ui": {"renderer": "bilibili_player", "version": 1},
        "data": {
            "keyword": keyword,
            "results": seasons,
            "selected_season_id": seasons[0]["season_id"] if seasons else None,
            "current_episode": 1,
        },
        "text": "x" * _TEXT_RESERVE_CHARS,
    }
    return len(json.dumps(payload, ensure_ascii=False))


def _fits(keyword: str, seasons: list[dict[str, Any]]) -> bool:
    return _payload_chars(keyword, seasons) <= _MAX_RESULT_CHARS


def _fit_episode_prefix(
    keyword: str,
    accepted: list[dict[str, Any]],
    card: dict[str, Any],
    episodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    lo = 0
    hi = len(episodes)
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        trial = {
            **card,
            "episodes": episodes[:mid],
            "episode_total": len(episodes),
            "episodes_truncated": True,
        }
        if _fits(keyword, [*accepted, trial]):
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return episodes[:best]


def _result_text(
    keyword: str,
    found: int,
    playable: list[dict[str, Any]],
    omitted: list[str],
) -> str:
    if found == 0:
        return f"未找到与「{keyword}」相关的番剧。"
    text = f"找到 {found} 部与「{keyword}」相关的番剧。"
    if not playable:
        return text + " 分集列表过长，未能展开播放器。"
    top = playable[0]
    total = int(top.get("episode_total") or len(top.get("episodes") or []))
    shown = len(top.get("episodes") or [])
    title = str(top.get("title") or "")
    if title:
        text += f" 默认选中《{title}》，共 {total} 集。"
    if top.get("episodes_truncated"):
        text += f" 播放器先载入前 {shown} 集。"
    if len(playable) > 1:
        text += f" 另有 {len(playable) - 1} 部可在播放器中切换。"
    if omitted:
        text += " 未展开分集：" + "、".join(omitted) + "。"
    return text


async def bilibili_search_anime(keyword: str, max_seasons: int = 5) -> str:
    """Search Bilibili bangumi (anime) by keyword and return playable episode lists.

    The Dashboard renders an in-chat player with season switching and episode
    navigation (official Bilibili iframe player). Episode lists are capped so the
    tool result stays inline instead of being evicted to a file.
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
    playable: list[dict[str, Any]] = []
    omitted: list[str] = []
    stop = False
    for item in results[:limit]:
        title = str(item.get("title") or item["season_id"])
        if stop:
            omitted.append(title)
            continue
        try:
            episodes = [_compact_episode(ep) for ep in _fetch_episodes(int(item["season_id"]))]
            error = ""
        except Exception as exc:
            logger.warning("season %s episodes failed: %s", item.get("season_id"), exc)
            episodes = []
            error = str(exc)
        card = _season_card(item, episodes)
        if error:
            card["episodes_error"] = error
        if _fits(keyword, [*playable, card]):
            playable.append(card)
            continue
        included_partial = False
        if not playable and episodes:
            fitted = _fit_episode_prefix(keyword, playable, card, episodes)
            truncated = {
                **card,
                "episodes": fitted,
                "episode_total": len(episodes),
                "episodes_truncated": True,
            }
            if fitted and _fits(keyword, [truncated]):
                playable.append(truncated)
                included_partial = True
        if not included_partial:
            omitted.append(title)
        stop = True

    selected = playable[0]["season_id"] if playable else None
    payload = {
        "octop_ui": {"renderer": "bilibili_player", "version": 1},
        "data": {
            "keyword": keyword,
            "results": playable,
            "selected_season_id": selected,
            "current_episode": 1,
        },
        "text": _result_text(keyword, len(results), playable, omitted),
    }
    return json.dumps(payload, ensure_ascii=False)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "bilibili_search_anime",
        bilibili_search_anime,
        description=(
            "在哔哩哔哩搜索番剧/动漫，并在聊天中渲染可播放的分集播放器。"
            "参数 keyword 为番剧名（如「葬送的芙莉莲」「进击的巨人」）。"
            "长剧集只展开最相关、放得进一次工具结果的分集，避免结果被截成文件。"
        ),
    )
