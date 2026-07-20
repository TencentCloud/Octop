"""Tencent News search gateway — official OpenAPI with API Key."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

OPENAPI_SEARCH_URL = "https://openapi.inews.qq.com/api/v1/agent/search"
# Match tencent-news-cli ≥1.0.14 (Caller-Skill + Skill-Request-Id are required by some keys).
_CALLER_SKILL = "octop_tencent-news_0.1"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_news",
        "description": "Search Tencent News articles by keyword",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results, default 10"},
                "max_results": {
                    "type": "integer",
                    "description": "Alias of limit, default 10",
                },
            },
            "required": ["query"],
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name == "search_news":
        return search_news(creds, args)
    raise ValueError(f"unknown tool: {name}")


def _api_key(creds: dict[str, Any]) -> str:
    # Prefer api_key; accept legacy ``cookie`` field from older connector instances.
    api_key = str(
        creds.get("api_key") or creds.get("cookie") or creds.get("auth_code") or ""
    ).strip()
    if not api_key:
        raise ValueError("请填写腾讯新闻 API Key")
    return api_key


def search_news(creds: dict[str, Any], args: dict[str, Any]) -> str:
    query = str(args.get("query") or "").strip()
    limit = int(args.get("limit") or args.get("max_results") or 10)
    if not query:
        raise ValueError("query is required")
    limit = max(1, min(limit, 50))
    request_id = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {_api_key(creds)}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "octop-connector/0.1",
        # Required by openapi.inews.qq.com for newer API-key cohorts (error 4010).
        "Skill-Request-Id": request_id,
        "Caller-Skill": _CALLER_SKILL,
    }
    # Official tencent-news-cli body shape (not a flat query string).
    body = {
        "page": 1,
        "page_size": limit,
        "is_show_content": 0,
        "query": {
            "query_id": request_id,
            "search": query,
        },
        "article_types": [0],
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(OPENAPI_SEARCH_URL, headers=headers, json=body)
        r.raise_for_status()
        payload = r.json()
    if not isinstance(payload, dict):
        return str(payload)
    base = payload.get("base_rsp")
    if isinstance(base, dict):
        code = base.get("code")
        if code not in (0, None, "0"):
            msg = str(base.get("msg") or base.get("message") or code)
            if code in (4006, "4006") or "apikey" in msg.lower() or "api key" in msg.lower():
                raise ValueError(f"腾讯新闻 API Key 无效: {msg}")
            raise ValueError(f"腾讯新闻接口错误 [{code}]: {msg}")
    return json.dumps(payload, ensure_ascii=False, indent=2)


def probe_credentials(creds: dict[str, Any]) -> None:
    """Validate API Key against the official OpenAPI search endpoint."""
    search_news(creds, {"query": "新闻", "limit": 1})
