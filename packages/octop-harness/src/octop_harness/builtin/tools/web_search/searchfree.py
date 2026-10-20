"""SearchFree — zero-config web search via the public ``searchfree.site`` API.

This is the only built-in web-search tool that needs **no API key and no
extra dependencies**. It's the natural default when the agent needs to
ground a response in the open web but the user hasn't configured Tavily
/ Brave / Google CSE / Kimi.

The endpoint is third-party — please respect their fair-use policy and
do not rely on it as your sole production search backend.
"""

from __future__ import annotations

import json
import os

import httpx
from langchain_core.tools import tool

DEFAULT_TIMEOUT = float(os.environ.get("SEARCHFREE_TIMEOUT", "30"))
DEFAULT_ENDPOINT = os.environ.get(
    "SEARCHFREE_ENDPOINT",
    "https://searchfree.site/api/search",
)


@tool
async def searchfree_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "advanced",
) -> str:
    """Search the open web via the free ``searchfree.site`` endpoint.

    Unlike Tavily / Brave / Google / Kimi, this tool needs no API key —
    it's the zero-config option you can always fall back to. Results are
    returned as a JSON array of ``{title, url, snippet, ...}`` dicts.

    Args:
        query: The search query string.
        max_results: Max number of results to return (default 5).
        search_depth: ``"basic"`` (faster) or ``"advanced"`` (default —
            does a richer retrieval pass on the upstream side).

    Returns:
        A JSON string with the search payload, or a plain-text error
        message when the upstream is unreachable / returns non-2xx.
    """
    payload = {
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(DEFAULT_ENDPOINT, json=payload)
    except httpx.HTTPError as exc:
        return f"Error: searchfree request failed: {exc}"

    if response.status_code >= 400:
        return f"Error: searchfree returned HTTP {response.status_code}."

    try:
        body = response.json()
    except ValueError:
        return "Error: searchfree returned a non-JSON response."

    # The upstream wraps the actual hits in ``{"results": [...]}`` — flatten
    # so the LLM sees an array directly. When a future deployment changes
    # the shape, fall back to returning the body verbatim.
    if isinstance(body, dict) and "results" in body:
        results = body.get("results") or []
        return json.dumps(results, ensure_ascii=False) if results else "No results found."
    return json.dumps(body, ensure_ascii=False) if body else "No results found."
