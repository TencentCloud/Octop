"""Search paper metadata through the official arXiv Atom API."""

from __future__ import annotations

import asyncio
import json
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from langgraph.config import get_config
from octop_harness.plugins import PluginContext

from octop.i18n import tr
from octop.infra.utils.locale import DEFAULT_LOCALE, normalize_locale

_API_URL = "https://export.arxiv.org/api/query"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}
_ARXIV_ID = re.compile(r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?")
_QUERY_FIELD = re.compile(r"(?:^|[\s(])(?:ti|au|abs|co|jr|cat|rn|id|all|submittedDate):")
_MIN_REQUEST_INTERVAL = 3.0
_request_lock = asyncio.Lock()
_last_request_at = 0.0


def _locale() -> str:
    try:
        config = get_config().get("configurable") or {}
    except RuntimeError:
        return DEFAULT_LOCALE
    return normalize_locale(str(config.get("locale") or DEFAULT_LOCALE))


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {
            "octop_ui": {"renderer": "arxiv_search_list", "version": 1},
            "data": data,
            "text": text,
        },
        ensure_ascii=False,
    )


def _identifier(query: str) -> str | None:
    candidate = re.sub(r"^(?:arxiv:|id:)\s*", "", query, flags=re.IGNORECASE)
    parsed = urlsplit(candidate)
    if parsed.hostname in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        for prefix in ("/abs/", "/pdf/"):
            if parsed.path.startswith(prefix):
                candidate = parsed.path.removeprefix(prefix).removesuffix(".pdf")
                break
    return candidate if _ARXIV_ID.fullmatch(candidate) else None


def _clean(value: str) -> str:
    return " ".join(value.split())


def _parse_feed(content: bytes, locale: str) -> tuple[list[dict[str, Any]], int]:
    root = ET.fromstring(content)
    if root.tag != f"{{{_NS['atom']}}}feed":
        raise ValueError(tr("plugins.arxiv_search.invalid_feed", locale))
    items: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", _NS):
        entry_url = entry.findtext("atom:id", "", _NS).strip()
        if urlsplit(entry_url).path.startswith("/api/errors"):
            raise ValueError(_clean(entry.findtext("atom:summary", "", _NS)))
        paper_id = _identifier(entry_url)
        if paper_id is None:
            continue
        category = entry.find("arxiv:primary_category", _NS)
        items.append(
            {
                "id": paper_id,
                "title": _clean(entry.findtext("atom:title", "", _NS)),
                "authors": [
                    _clean(author.findtext("atom:name", "", _NS))
                    for author in entry.findall("atom:author", _NS)
                ],
                "summary": _clean(entry.findtext("atom:summary", "", _NS)),
                "published": entry.findtext("atom:published", "", _NS),
                "updated": entry.findtext("atom:updated", "", _NS),
                "categories": [cat.get("term", "") for cat in entry.findall("atom:category", _NS)],
                "primary_category": category.get("term", "") if category is not None else "",
                "url": f"https://arxiv.org/abs/{paper_id}",
                "pdf_url": f"https://arxiv.org/pdf/{paper_id}",
                "doi": _clean(entry.findtext("arxiv:doi", "", _NS)),
                "journal_ref": _clean(entry.findtext("arxiv:journal_ref", "", _NS)),
            },
        )
    total = int(root.findtext("opensearch:totalResults", str(len(items)), _NS))
    return items, total


async def search_arxiv(
    query: str,
    limit: int = 5,
    start: int = 0,
    sort_by: Literal["relevance", "lastUpdatedDate", "submittedDate"] = "relevance",
    sort_order: Literal["ascending", "descending"] = "descending",
) -> str:
    """Search keywords, an arXiv field query, or a paper ID/URL; return full abstracts."""
    global _last_request_at
    locale = _locale()
    q = query.strip()
    offset = max(0, start)
    data: dict[str, Any] = {"query": q, "items": [], "total": 0, "start": offset}
    if not q:
        return _payload(
            {**data, "error": "empty_query"}, tr("plugins.arxiv_search.empty_query", locale)
        )
    if sort_by not in {"relevance", "lastUpdatedDate", "submittedDate"} or sort_order not in {
        "ascending",
        "descending",
    }:
        return _payload(
            {**data, "error": "invalid_sort"}, tr("plugins.arxiv_search.invalid_sort", locale)
        )
    n = max(1, min(limit, 20))
    params: dict[str, str | int] = {
        "start": offset,
        "max_results": n,
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }
    paper_id = _identifier(q)
    if paper_id:
        params["id_list"] = paper_id
    else:
        params["search_query"] = q if _QUERY_FIELD.search(q) else f"all:{q}"
    try:
        async with _request_lock:
            delay = _MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
            if delay > 0:
                await asyncio.sleep(delay)
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Octop-arxiv-search/0.1.0",
                    "Accept": "application/atom+xml",
                },
                follow_redirects=True,
            ) as client:
                _last_request_at = time.monotonic()
                response = await client.get(_API_URL, params=params)
                response.raise_for_status()
        items, total = _parse_feed(response.content, locale)
    except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
        return _payload(
            {**data, "error": str(exc)}, tr("plugins.arxiv_search.failed", locale, error=str(exc))
        )
    items = items[:n]
    data.update(items=items, total=total)
    if not items:
        return _payload(data, tr("plugins.arxiv_search.no_results", locale, query=q))
    lines = [tr("plugins.arxiv_search.results", locale, query=q, count=len(items), total=total)]
    for index, item in enumerate(items, start=offset + 1):
        lines.append(
            tr(
                "plugins.arxiv_search.paper",
                locale,
                index=index,
                title=item["title"],
                authors=", ".join(item["authors"]),
                summary=item["summary"],
                url=item["url"],
                pdf_url=item["pdf_url"],
            ),
        )
    return _payload(data, "\n\n".join(lines))


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "search_arxiv",
        search_arxiv,
        description=tr("plugins.arxiv_search.tool_description", "en"),
    )
