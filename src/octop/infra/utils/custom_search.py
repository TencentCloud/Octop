"""HTTP transport shared by custom search probes and agent tools."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from octop.infra.utils.ssrf_guard import validate_https_url_resolved


async def request_custom_search(
    env_vars: Mapping[str, str], query: str, max_results: int = 5
) -> dict[str, Any]:
    """Call a Tavily-compatible or Baidu Qianfan web-search endpoint."""
    url = env_vars.get("CUSTOM_SEARCH_URL", "").strip()
    api_key = env_vars.get("CUSTOM_SEARCH_API_KEY", "").strip()
    protocol = env_vars.get("CUSTOM_SEARCH_PROTOCOL", "tavily").strip()
    if not url or not api_key:
        raise ValueError("CUSTOM_SEARCH_URL and CUSTOM_SEARCH_API_KEY are required")
    if protocol not in {"tavily", "qianfan"}:
        raise ValueError("CUSTOM_SEARCH_PROTOCOL must be tavily or qianfan")
    await validate_https_url_resolved(url)
    payload: dict[str, Any]
    if protocol == "qianfan":
        payload = {
            "messages": [{"role": "user", "content": query}],
            "resource_type_filter": [{"type": "web", "top_k": max_results}],
        }
    else:
        payload = {"query": query, "max_results": max_results, "search_depth": "basic"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url, headers={"Authorization": f"Bearer {api_key}"}, json=payload
        )
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, dict):
        raise ValueError("invalid search response")
    results = body.get("references" if protocol == "qianfan" else "results")
    if not isinstance(results, list):
        raise ValueError("search response must contain a results/references list")
    return {"results": results}
