"""GitHub trending repositories via Search API."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import httpx
from harness_agent.plugins import PluginContext

_UA = "Octop-github-trending/0.1.0"


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {
            "octop_ui": {"renderer": "github_trending_list", "version": 1},
            "data": data,
            "text": text,
        },
        ensure_ascii=False,
    )


def _since_date(since: str) -> date:
    key = (since or "daily").strip().lower()
    days = {"daily": 1, "weekly": 7, "monthly": 30}.get(key, 1)
    return date.today() - timedelta(days=days)


async def github_trending(language: str = "", since: str = "daily", limit: int = 10) -> str:
    """Fetch trending GitHub repos created recently, sorted by stars."""
    n = max(1, min(int(limit or 10), 30))
    created_after = _since_date(since)
    q = f"created:>{created_after.isoformat()}"
    lang = (language or "").strip()
    if lang:
        q += f" language:{lang}"
    headers = {
        "User-Agent": _UA,
        "Accept": "application/vnd.github+json",
    }
    try:
        with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True) as client:
            resp = client.get(
                "https://api.github.com/search/repositories",
                params={"q": q, "sort": "stars", "order": "desc", "per_page": n},
            )
            resp.raise_for_status()
            body = resp.json()
    except Exception as exc:
        return _payload(
            {"items": [], "error": str(exc), "since": since, "language": lang},
            f"获取 GitHub 趋势失败：{exc}",
        )
    items: list[dict[str, Any]] = []
    for row in body.get("items") or []:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "name": str(row.get("name") or ""),
                "full_name": str(row.get("full_name") or ""),
                "url": str(row.get("html_url") or ""),
                "stars": int(row.get("stargazers_count") or 0),
                "description": str(row.get("description") or "")[:200],
                "language": str(row.get("language") or ""),
            },
        )
        if len(items) >= n:
            break
    if not items:
        return _payload({"items": [], "silent": True, "since": since, "language": lang}, "")
    lines = [f"⭐ {r['stars']} {r['full_name']}" for r in items[:8]]
    text = f"GitHub 趋势 ({since}) {len(items)} 个仓库\n" + "\n".join(lines)
    return _payload({"items": items, "since": since, "language": lang}, text)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "github_trending",
        github_trending,
        description=(
            "GitHub 新星仓库排行。language 可选编程语言；since 为 daily/weekly/monthly；"
            "limit 条数默认 10。"
        ),
    )
