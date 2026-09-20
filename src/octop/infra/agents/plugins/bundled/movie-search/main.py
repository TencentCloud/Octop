"""Bangumi subject search for movies and anime."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx
from harness_agent.plugins import PluginContext

_UA = "Octop-movie-search/0.1.0 (https://github.com/octop)"


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "movie_search_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _search(
    client: httpx.Client, query: str, subject_type: int, limit: int
) -> list[dict[str, Any]]:
    path = quote(query.strip(), safe="")
    resp = client.get(
        f"https://api.bgm.tv/search/subject/{path}",
        params={"type": subject_type, "responseGroup": "small", "max_results": limit},
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("list") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = row.get("id")
        title = str(row.get("name") or row.get("name_cn") or "").strip()
        if not title:
            continue
        rating = row.get("rating")
        score_raw = row.get("score")
        if score_raw is None and isinstance(rating, dict):
            score_raw = rating.get("score")
        score = float(score_raw) if score_raw is not None else None
        image = str(row.get("images", {}).get("large") or row.get("images", {}).get("medium") or "")
        summary = str(row.get("summary") or "")[:160]
        url = f"https://bgm.tv/subject/{sid}" if sid else ""
        out.append({"title": title, "score": score, "url": url, "image": image, "summary": summary})
        if len(out) >= limit:
            break
    return out


async def search_movie(query: str, limit: int = 5) -> str:
    """Search Bangumi for movies (type 6) with anime fallback (type 2)."""
    q = (query or "").strip()
    if not q:
        return _payload({"items": [], "error": "empty query"}, "请提供搜索关键词。")
    n = max(1, min(int(limit or 5), 15))
    headers = {"User-Agent": _UA}
    try:
        with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True) as client:
            items = _search(client, q, 6, n)
            source = "movie"
            if not items:
                items = _search(client, q, 2, n)
                source = "anime"
    except Exception as exc:
        return _payload({"items": [], "error": str(exc)}, f"搜索失败：{exc}")
    if not items:
        return _payload({"items": [], "query": q, "silent": True}, "")
    lines = [f"{r['title']} ({r['score'] or '—'})" for r in items[:5]]
    text = f"Bangumi「{q}」{len(items)} 条\n" + "\n".join(lines)
    return _payload({"items": items, "query": q, "source": source}, text)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "search_movie",
        search_movie,
        description="在 Bangumi 搜索电影或动画。query 为关键词，limit 默认 5。",
    )
