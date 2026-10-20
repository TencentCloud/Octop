"""DeepSeek web search tool. Requires ``DEEPSEEK_API_KEY``.

Uses the standalone DeepSeek search API (``POST /v1/tools/search``).
Queries support ``site:`` / ``-site:`` operators.
"""

from __future__ import annotations

import json
import os

import httpx
from langchain_core.tools import tool

_SEARCH_URL = "https://api.deepseek.com/v1/tools/search"


@tool
async def deepseek_search(
    query: str,
    max_results: int = 5,
) -> str:
    """Search the web with DeepSeek Search.

    Args:
        query: The search query string (1-128 chars; supports ``site:`` and
            ``-site:`` operators and quoted exact phrases).
        max_results: Maximum number of results to return (default 5, max 50).

    Returns:
        A JSON string with the trimmed results, or a plain-text error if
        the API key is missing or the API reports an error.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return "Error: DEEPSEEK_API_KEY environment variable is not set."

    payload = {
        "query": query[:128],
        "count": max(1, min(max_results, 50)),
        "need_content": False,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                _SEARCH_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        return f"Error: deepseek_search request failed: {exc}"

    try:
        data = response.json()
    except ValueError:
        return f"Error: deepseek_search returned invalid JSON (HTTP {response.status_code})."

    if response.status_code >= 400:
        detail = response.text[:300]
        return f"Error: deepseek_search failed (HTTP {response.status_code}): {detail}"

    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return "Error: deepseek_search returned no results payload."

    trimmed = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("summary") or item.get("snippet", ""),
            "date": item.get("date", ""),
            "site": item.get("site_name", ""),
            "rerank_score": item.get("rerank_score"),
        }
        for item in results
        if isinstance(item, dict)
    ]
    return json.dumps({"results": trimmed}, ensure_ascii=False)
