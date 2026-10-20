"""Exa web search tool. Requires ``EXA_API_KEY``.

Uses the Exa search API (``POST https://api.exa.ai/search``) with
highlight contents enabled so results carry query-relevant excerpts.
"""

from __future__ import annotations

import json
import os

import httpx
from langchain_core.tools import tool

_SEARCH_URL = "https://api.exa.ai/search"


@tool
async def exa_search(
    query: str,
    max_results: int = 5,
) -> str:
    """Search the web with Exa.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default 5, max 20).

    Returns:
        A JSON string with the trimmed results, or a plain-text error if
        the API key is missing or the API reports an error.
    """
    api_key = os.getenv("EXA_API_KEY", "")
    if not api_key:
        return "Error: EXA_API_KEY environment variable is not set."

    payload = {
        "query": query,
        "numResults": max(1, min(max_results, 20)),
        "contents": {"highlights": True},
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                _SEARCH_URL,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        return f"Error: exa_search request failed: {exc}"

    try:
        data = response.json()
    except ValueError:
        return f"Error: exa_search returned invalid JSON (HTTP {response.status_code})."

    if response.status_code >= 400:
        detail = response.text[:300]
        return f"Error: exa_search failed (HTTP {response.status_code}): {detail}"

    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return "Error: exa_search returned no results payload."

    trimmed = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": " ".join(item.get("highlights") or []) or item.get("text", ""),
            "published_date": item.get("publishedDate", ""),
            "author": item.get("author", ""),
        }
        for item in results
        if isinstance(item, dict)
    ]
    return json.dumps({"results": trimmed}, ensure_ascii=False)
