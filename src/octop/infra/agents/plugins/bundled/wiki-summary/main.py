"""Wikipedia REST summary with opensearch fallback."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx
from harness_agent.plugins import PluginContext

_UA = "Octop-wiki-summary/0.1.0"


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "wiki_summary_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _summary(client: httpx.Client, lang: str, title: str) -> dict[str, Any]:
    path = quote(title.replace(" ", "_"), safe="")
    resp = client.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{path}")
    if resp.status_code == 404:
        return {}
    resp.raise_for_status()
    body = resp.json()
    thumb = body.get("thumbnail") or {}
    return {
        "title": str(body.get("title") or title),
        "extract": str(body.get("extract") or "")[:600],
        "url": str(
            body.get("content_urls", {}).get("desktop", {}).get("page")
            or body.get("content_urls", {}).get("mobile", {}).get("page")
            or ""
        ),
        "thumbnail": str(thumb.get("source") or ""),
    }


def _opensearch_title(client: httpx.Client, lang: str, query: str) -> str | None:
    resp = client.get(
        f"https://{lang}.wikipedia.org/w/api.php",
        params={"action": "opensearch", "search": query, "limit": 1, "format": "json"},
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list) and len(data) >= 2 and data[1]:
        titles = data[1]
        if titles:
            return str(titles[0])
    return None


async def wiki_summary(query: str, lang: str = "zh") -> str:
    """Fetch Wikipedia summary; opensearch if direct title misses."""
    q = (query or "").strip()
    if not q:
        return _payload({"error": "empty"}, "请提供词条名或关键词。")
    language = (lang or "zh").strip().lower() or "zh"
    headers = {"User-Agent": _UA}
    try:
        with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True) as client:
            row = _summary(client, language, q)
            if not row.get("extract"):
                alt = _opensearch_title(client, language, q)
                if alt:
                    row = _summary(client, language, alt)
    except Exception as exc:
        return _payload({"error": str(exc), "query": q}, f"维基查询失败：{exc}")
    if not row.get("extract"):
        return _payload({"query": q, "silent": True}, "")
    text = f"{row['title']}：{row['extract'][:120]}…"
    return _payload({**row, "query": q, "lang": language}, text)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "wiki_summary",
        wiki_summary,
        description="维基百科摘要。query 为词条；lang 默认 zh。",
    )
