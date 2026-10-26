"""Brave Search tool. Requires ``BRAVE_API_KEY``.

Brave runs an independent index and is privacy-friendly. The
``langchain-community`` integration only exposes a synchronous client,
so we hop to a thread to keep the agent loop unblocked.
"""

from __future__ import annotations

import asyncio
import json
import os

from langchain_core.tools import tool


@tool
async def brave_search(
    query: str,
    count: int = 5,
) -> str:
    """Search the web with Brave Search.

    Args:
        query: The search query string.
        count: Number of results to return (default 5, max 20).

    Returns:
        Either a JSON string / plain text with the results, or an error
        message if the API key is missing or the package is not
        installed.
    """
    api_key = os.getenv("BRAVE_API_KEY", "")
    if not api_key:
        return "Error: BRAVE_API_KEY environment variable is not set."

    try:
        from langchain_community.tools import BraveSearch
    except ImportError:
        return (
            "Error: brave_search requires the 'langchain-community' package. "
            "Install with: pip install 'octop-harness[brave]' "
            "(or: pip install langchain-community)."
        )

    search = BraveSearch.from_api_key(
        api_key=api_key,
        search_kwargs={"count": count},
    )
    # BraveSearch only exposes ``.run()``; off-load to a thread so the
    # event loop keeps spinning while the HTTP call is in flight.
    result = await asyncio.get_event_loop().run_in_executor(None, search.run, query)
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
