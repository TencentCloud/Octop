"""Public hot lists: Weibo, Zhihu, Hacker News."""

from __future__ import annotations

import json
from typing import Any

import httpx
from harness_agent.plugins import PluginContext

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "hot_topics_list", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _client(**extra_headers: str) -> httpx.Client:
    headers = {"User-Agent": _UA, **extra_headers}
    return httpx.Client(timeout=15.0, headers=headers, follow_redirects=True)


def _weibo(limit: int) -> list[dict[str, Any]]:
    # Without Referer this endpoint returns 403 for server-side clients.
    with _client(Referer="https://weibo.com/") as client:
        resp = client.get("https://weibo.com/ajax/side/hotSearch")
        resp.raise_for_status()
        payload = resp.json()
    realtime = ((payload.get("data") or {}).get("realtime")) or []
    items: list[dict[str, Any]] = []
    for row in realtime:
        if not isinstance(row, dict):
            continue
        title = str(row.get("note") or row.get("word") or "").strip()
        if not title:
            continue
        word = str(row.get("word") or title)
        items.append(
            {
                "rank": len(items) + 1,
                "title": title,
                "url": f"https://s.weibo.com/weibo?q={word}",
                "extra": str(row.get("num") or ""),
            },
        )
        if len(items) >= limit:
            break
    return items


def _zhihu(limit: int) -> list[dict[str, Any]]:
    # www.zhihu.com/api/v3/... requires login (401). The mobile API is public.
    with _client(Referer="https://www.zhihu.com/") as client:
        resp = client.get(
            "https://api.zhihu.com/topstory/hot-list",
            params={"limit": min(limit, 50)},
        )
        resp.raise_for_status()
        payload = resp.json()
    items: list[dict[str, Any]] = []
    for row in payload.get("data") or []:
        if not isinstance(row, dict):
            continue
        target = row.get("target") or {}
        if not isinstance(target, dict):
            continue
        title = str(target.get("title") or "").strip()
        if not title:
            continue
        qid = target.get("id")
        url = str(target.get("url") or "")
        if qid:
            url = f"https://www.zhihu.com/question/{qid}"
        elif "api.zhihu.com/questions/" in url:
            url = url.replace("https://api.zhihu.com/questions/", "https://www.zhihu.com/question/")
        items.append(
            {
                "rank": len(items) + 1,
                "title": title,
                "url": url,
                "extra": str(row.get("detail_text") or ""),
            },
        )
        if len(items) >= limit:
            break
    return items


def _hn(limit: int) -> list[dict[str, Any]]:
    with _client() as client:
        ids = client.get("https://hacker-news.firebaseio.com/v0/topstories.json").json()
        if not isinstance(ids, list):
            return []
        items: list[dict[str, Any]] = []
        for hid in ids[:limit]:
            story = client.get(f"https://hacker-news.firebaseio.com/v0/item/{hid}.json").json()
            if not isinstance(story, dict):
                continue
            title = str(story.get("title") or "").strip()
            if not title:
                continue
            url = str(story.get("url") or f"https://news.ycombinator.com/item?id={hid}")
            score = story.get("score")
            items.append(
                {
                    "rank": len(items) + 1,
                    "title": title,
                    "url": url,
                    "extra": f"{score} pts" if score is not None else "",
                },
            )
        return items


async def get_hot_topics(source: str = "weibo", limit: int = 20) -> str:
    """Fetch a public hot list. source: weibo | zhihu | hn."""
    src = (source or "weibo").strip().lower()
    if src in {"hackernews", "hacker-news"}:
        src = "hn"
    n = max(1, min(int(limit or 20), 30))
    fetchers = {"weibo": _weibo, "zhihu": _zhihu, "hn": _hn}
    if src not in fetchers:
        return _payload(
            {"source": src, "items": [], "error": "unknown source"},
            "source 仅支持 weibo、zhihu、hn。",
        )
    try:
        items = fetchers[src](n)
    except Exception:
        return _payload(
            {"source": src, "items": [], "silent": True},
            "",
        )
    if not items:
        return _payload({"source": src, "items": [], "silent": True}, "")
    lines = [f"{row['rank']}. {row['title']}" for row in items[:10]]
    text = f"{src} 热榜 {len(items)} 条\n" + "\n".join(lines)
    return _payload({"source": src, "items": items}, text)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "get_hot_topics",
        get_hot_topics,
        description=(
            "获取热榜。source 为 weibo（微博）、zhihu（知乎）或 hn（Hacker News），"
            "limit 为条数（默认 20，最大 30）。"
        ),
    )
