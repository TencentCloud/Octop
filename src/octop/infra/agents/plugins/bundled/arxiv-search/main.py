"""Search arXiv papers through its public Atom API."""

from __future__ import annotations

import asyncio
import json
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from harness_agent.plugins import PluginContext

_API_URL = "https://export.arxiv.org/api/query"
_UA = "Octop-arxiv-search/0.1.0"
_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"
_OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"
_SEARCH_RENDERER = "arxiv_search_results"
_PAPER_RENDERER = "arxiv_paper_card"
_ARXIV_RETRY_DELAY_SECONDS = 3.0
_CATEGORY = re.compile(r"[a-z-]+(?:\.[A-Za-z-]+)?")
_NEW_ID = re.compile(r"\d{4}\.\d{4,5}(?:v\d+)?")
_OLD_ID = re.compile(r"[A-Za-z-]+(?:\.[A-Za-z-]+)?/\d{7}(?:v\d+)?")
_SORTS = {
    "submitted": "submittedDate",
    "updated": "lastUpdatedDate",
    "relevance": "relevance",
}


def _payload(renderer: str, data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": renderer, "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _error(
    renderer: str,
    code: str,
    text: str,
    **data: Any,
) -> str:
    return _payload(renderer, {"error": code, **data}, text)


def _bounded_int(value: int, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _quote_query(query: str) -> str:
    """Make a user phrase safe to embed in arXiv's Lucene query syntax."""
    return query.replace("\\", "\\\\").replace('"', '\\"')


def _is_paper_id(value: str) -> bool:
    return bool(_NEW_ID.fullmatch(value) or _OLD_ID.fullmatch(value))


def _paper_id_from_url(value: str) -> str:
    return value.rsplit("/abs/", 1)[-1].strip()


def _optional_text(entry: ET.Element, tag: str) -> str | None:
    value = _clean_text(entry.findtext(tag))
    return value or None


def _paper_from_entry(entry: ET.Element) -> dict[str, Any] | None:
    raw_id = _clean_text(entry.findtext(f"{_ATOM}id"))
    paper_id = _paper_id_from_url(raw_id)
    if not _is_paper_id(paper_id):
        return None

    authors = [
        name
        for author in entry.findall(f"{_ATOM}author")
        if (name := _clean_text(author.findtext(f"{_ATOM}name")))
    ]
    categories = [
        term.strip()
        for category in entry.findall(f"{_ATOM}category")
        if (term := category.get("term")) and term.strip()
    ]
    versions = entry.findall(f"{_ARXIV}version")
    latest_version = versions[-1].get("version") if versions else None
    primary_category = entry.find(f"{_ARXIV}primary_category")

    return {
        "id": paper_id,
        "title": _clean_text(entry.findtext(f"{_ATOM}title")),
        "authors": authors,
        "summary": _clean_text(entry.findtext(f"{_ATOM}summary")),
        "categories": categories,
        "primary_category": (primary_category.get("term") if primary_category is not None else ""),
        "published": _clean_text(entry.findtext(f"{_ATOM}published")),
        "updated": _clean_text(entry.findtext(f"{_ATOM}updated")),
        "version": latest_version or "",
        "abs_url": f"https://arxiv.org/abs/{paper_id}",
        "pdf_url": f"https://arxiv.org/pdf/{paper_id}",
        "doi": _optional_text(entry, f"{_ARXIV}doi"),
        "journal_ref": _optional_text(entry, f"{_ARXIV}journal_ref"),
        "comment": _optional_text(entry, f"{_ARXIV}comment"),
    }


def _parse_feed(body: str) -> tuple[list[dict[str, Any]], int]:
    root = ET.fromstring(body)
    papers = [
        paper
        for entry in root.findall(f"{_ATOM}entry")
        if (paper := _paper_from_entry(entry)) is not None
    ]
    try:
        total = int(_clean_text(root.findtext(f"{_OPENSEARCH}totalResults")) or len(papers))
    except ValueError:
        total = len(papers)
    return papers, total


async def _fetch(params: dict[str, str | int]) -> tuple[list[dict[str, Any]], int]:
    headers = {"User-Agent": _UA, "Accept": "application/atom+xml"}
    for attempt in range(2):
        # A fresh client avoids retrying through a potentially sticky edge connection.
        async with httpx.AsyncClient(
            timeout=20.0, headers=headers, follow_redirects=True
        ) as client:
            response = await client.get(_API_URL, params=params)
        if response.status_code == 406 and attempt == 0:
            # arXiv asks API clients to leave three seconds between successive requests.
            await asyncio.sleep(_ARXIV_RETRY_DELAY_SECONDS)
            continue
        response.raise_for_status()
        return _parse_feed(response.text)
    raise AssertionError("unreachable")


def _search_text(items: list[dict[str, Any]], *, total: int, query: str) -> str:
    if not items:
        return "未找到匹配的 arXiv 论文。"
    lines = [f"arXiv 搜索结果：显示 {len(items)} / {total} 篇（关键词：{query}）"]
    for index, paper in enumerate(items, start=1):
        authors = ", ".join(paper["authors"][:5]) or "未知作者"
        summary = paper["summary"]
        preview = f"{summary[:500]}…" if len(summary) > 500 else summary
        lines.extend(
            [
                f"{index}. {paper['title']} ({paper['id']})",
                f"作者：{authors}",
                f"摘要：{preview}",
                f"链接：{paper['abs_url']} · PDF：{paper['pdf_url']}",
            ]
        )
    return "\n".join(lines)


def _paper_text(paper: dict[str, Any]) -> str:
    authors = ", ".join(paper["authors"]) or "未知作者"
    lines = [
        f"{paper['title']} ({paper['id']})",
        f"作者：{authors}",
        f"分类：{', '.join(paper['categories']) or '未提供'}",
        f"首发：{paper['published'] or '未提供'}；更新：{paper['updated'] or '未提供'}",
        f"摘要：{paper['summary'] or '未提供'}",
        f"链接：{paper['abs_url']} · PDF：{paper['pdf_url']}",
    ]
    if paper["doi"]:
        lines.append(f"DOI：{paper['doi']}")
    if paper["journal_ref"]:
        lines.append(f"期刊引用：{paper['journal_ref']}")
    if paper["comment"]:
        lines.append(f"备注：{paper['comment']}")
    return "\n".join(lines)


async def arxiv_search(
    query: str,
    category: str = "",
    limit: int = 10,
    offset: int = 0,
    sort: str = "submitted",
) -> str:
    """Search arXiv by keywords, optionally restricted to one subject category."""
    q = _clean_text(query)
    renderer = _SEARCH_RENDERER
    if not q:
        return _error(renderer, "empty_query", "请提供论文关键词。")
    if len(q) > 256:
        return _error(renderer, "query_too_long", "关键词不能超过 256 个字符。", query=q)

    cat = _clean_text(category)
    if cat and not _CATEGORY.fullmatch(cat):
        return _error(
            renderer,
            "invalid_category",
            "分类无效，请使用 cs.AI、stat.ML 或 cond-mat.dis-nn 这样的 arXiv 分类。",
            query=q,
            category=cat,
        )
    sort_key = _clean_text(sort or "submitted").lower()
    if sort_key not in _SORTS:
        return _error(
            renderer,
            "invalid_sort",
            "sort 只支持 submitted、updated 或 relevance。",
            query=q,
            sort=sort_key,
        )

    result_limit = _bounded_int(limit, default=10, minimum=1, maximum=20)
    result_offset = _bounded_int(offset, default=0, minimum=0, maximum=29_980)
    search_query = f'all:"{_quote_query(q)}"'
    if cat:
        search_query += f" AND cat:{cat}"
    params: dict[str, str | int] = {
        "search_query": search_query,
        "start": result_offset,
        "max_results": result_limit,
        "sortBy": _SORTS[sort_key],
        "sortOrder": "descending",
    }
    try:
        papers, total = await _fetch(params)
    except ET.ParseError as exc:
        return _error(renderer, "invalid_response", "arXiv 返回了无法解析的数据。", detail=str(exc))
    except Exception as exc:
        return _error(renderer, "request_failed", f"查询 arXiv 失败：{exc}", detail=str(exc))

    data = {
        "items": papers,
        "query": q,
        "category": cat,
        "limit": result_limit,
        "offset": result_offset,
        "sort": sort_key,
        "total_results": total,
        "empty": not papers,
    }
    return _payload(renderer, data, _search_text(papers, total=total, query=q))


async def arxiv_paper(arxiv_id: str) -> str:
    """Retrieve one arXiv paper by a modern or legacy arXiv identifier."""
    renderer = _PAPER_RENDERER
    paper_id = _clean_text(arxiv_id)
    if not _is_paper_id(paper_id):
        return _error(
            renderer,
            "invalid_id",
            "论文 ID 无效，请使用 2501.12345、2501.12345v2 或 hep-th/9901001。",
            arxiv_id=paper_id,
        )
    try:
        papers, _ = await _fetch({"id_list": paper_id, "max_results": 1})
    except ET.ParseError as exc:
        return _error(renderer, "invalid_response", "arXiv 返回了无法解析的数据。", detail=str(exc))
    except Exception as exc:
        return _error(renderer, "request_failed", f"查询 arXiv 失败：{exc}", detail=str(exc))
    if not papers:
        return _payload(
            renderer,
            {"arxiv_id": paper_id, "empty": True},
            "未找到这篇 arXiv 论文。",
        )
    paper = papers[0]
    return _payload(renderer, {"paper": paper, "arxiv_id": paper_id}, _paper_text(paper))


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "arxiv_search",
        arxiv_search,
        description=(
            "检索 arXiv 论文。query 为关键词；category 可选分类（如 cs.AI）；"
            "sort 支持 submitted、updated、relevance，默认最新投稿。"
        ),
    )
    ctx.tool(
        "arxiv_paper",
        arxiv_paper,
        description="按单个 arXiv ID 查询论文详情，例如 2501.12345 或 hep-th/9901001。",
    )
