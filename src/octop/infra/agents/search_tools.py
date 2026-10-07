"""Custom web search mounted through the harness public tools interface."""

from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.tools import tool

from octop.infra.utils.custom_search import request_custom_search


def build_custom_search_tools() -> list[Any]:
    if not os.getenv("CUSTOM_SEARCH_URL") or not os.getenv("CUSTOM_SEARCH_API_KEY"):
        return []

    @tool
    async def custom_search(query: str, max_results: int = 5) -> str:
        """Search the web using the configured custom search provider."""
        result = await request_custom_search(os.environ, query, max(1, min(max_results, 20)))
        return json.dumps(result, ensure_ascii=False)

    return [custom_search]
