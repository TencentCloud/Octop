"""Doubao (Volcengine) web search tool. Requires ``DOUBAO_SEARCH_API_KEY``.

Uses the Doubao Search Global edition: a single Bearer API key, pay-per-use.
Request/response fields are PascalCase (``Query`` / ``Result.Documents``).
"""

from __future__ import annotations

import json
import os

import httpx
from langchain_core.tools import tool

_SEARCH_URL = "https://open.feedcoopapi.com/search_api/global_search"
_MAX_SNIPPET_LENGTH = 1000


@tool
async def doubao_search(
    query: str,
    max_results: int = 5,
) -> str:
    """Search the web with Doubao (Volcengine) Search.

    Args:
        query: The search query string (1-100 chars; longer is truncated).
        max_results: Maximum number of results to return (default 5, max 20).

    Returns:
        A JSON string with the trimmed results, or a plain-text error if
        the API key is missing or the API reports an error.
    """
    api_key = os.getenv("DOUBAO_SEARCH_API_KEY", "")
    if not api_key:
        return "Error: DOUBAO_SEARCH_API_KEY environment variable is not set."

    payload = {
        "SearchType": "web",
        "Query": query[:100],
        "DocCount": max(1, min(max_results, 20)),
        "MaxSnippetLength": _MAX_SNIPPET_LENGTH,
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
        return f"Error: doubao_search request failed: {exc}"

    try:
        data = response.json()
    except ValueError:
        return f"Error: doubao_search returned invalid JSON (HTTP {response.status_code})."

    if response.status_code >= 400:
        meta = data.get("ResponseMetadata") if isinstance(data, dict) else None
        err = meta.get("Error") if isinstance(meta, dict) else None
        code = err.get("Code") if isinstance(err, dict) else response.status_code
        message = err.get("Message") if isinstance(err, dict) else response.text[:300]
        return f"Error: doubao_search failed ({code}): {message}"

    result = data.get("Result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        return "Error: doubao_search returned no Result payload."
    err_code = result.get("ErrorCode")
    if err_code not in (None, 0, "0"):
        return f"Error: doubao_search failed ({err_code}): {result.get('ErrorMsg', '')}"

    documents = result.get("Documents") or []
    trimmed = []
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        snippets = [
            part.get("Text", "")
            for part in (doc.get("Snippet") or [])
            if isinstance(part, dict) and part.get("Type") == "text"
        ]
        host = doc.get("HostInfo") if isinstance(doc.get("HostInfo"), dict) else {}
        trimmed.append(
            {
                "title": doc.get("Title", ""),
                "url": doc.get("Url", ""),
                "snippet": "\n".join(text for text in snippets if text),
                "publish_time": (doc.get("DocumentInfo") or {}).get("PublishTime", ""),
                "site": host.get("Hostname", ""),
                "authority": host.get("AuthorityLevel", ""),
            }
        )
    return json.dumps(
        {"results": trimmed, "total": result.get("TotalDocCount", len(trimmed))},
        ensure_ascii=False,
    )
