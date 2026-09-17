"""You.com web search via the You.com MCP endpoint (free or API key)."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from harness_agent.plugins import PluginContext, get_tool_config

_ENDPOINT_KEYLESS = "https://api.you.com/mcp?profile=free"
_ENDPOINT_AUTHED = "https://api.you.com/mcp"
_TIMEOUT_S = 20.0


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "you_search_list", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _api_key() -> str:
    """Per-agent tool config wins; the YDC_API_KEY env var is the fallback."""
    try:
        cfg = get_tool_config("you_search") or {}
        key = str(cfg.get("api_key") or "").strip()
        if key:
            return key
    except Exception:
        pass
    return str(os.environ.get("YDC_API_KEY", "")).strip()


def _endpoint() -> tuple[str, dict[str, str]]:
    key = _api_key()
    if key:
        return _ENDPOINT_AUTHED, {"Authorization": f"Bearer {key}"}
    return _ENDPOINT_KEYLESS, {}


def _parse_web_results(payload: Any) -> list[dict[str, Any]]:
    """Extract ``results.web[]`` from a you-search tool-call result."""
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, dict):
        return []
    web = results.get("web")
    if not isinstance(web, list):
        return []
    items: list[dict[str, Any]] = []
    for row in web:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        title = str(row.get("title") or "").strip()
        if not url or not title:
            continue
        items.append(
            {
                "rank": len(items) + 1,
                "title": title,
                "url": url,
                "extra": str(row.get("page_age") or "")[:10],
            },
        )
    return items


def _result_text(content: Any) -> str:
    """Return the first text part of an MCP tool-call result."""
    for part in content or []:
        if isinstance(part, dict) and part.get("type") == "text":
            return str(part.get("text") or "")
    return ""


def _rpc_payload(resp: httpx.Response) -> Any:
    """Return the JSON-RPC payload from a JSON or SSE-framed response.

    The You.com MCP endpoint answers ``text/event-stream`` with one
    ``data:`` line per JSON-RPC message; some proxies return plain JSON.
    """
    ctype = (resp.headers.get("content-type") or "").lower()
    if "text/event-stream" in ctype:
        for line in resp.text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            try:
                message = json.loads(line[5:].strip())
            except ValueError:
                continue
            if isinstance(message, dict) and "result" in message:
                return message
        return {}
    return resp.json()


def _search(query: str, max_results: int) -> list[dict[str, Any]]:
    endpoint, headers = _endpoint()
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "you-search",
            "arguments": {"query": query, "max_results": max_results},
        },
    }
    with httpx.Client(timeout=_TIMEOUT_S) as client:
        resp = client.post(
            endpoint,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                **headers,
            },
            json=body,
        )
        resp.raise_for_status()
        payload = _rpc_payload(resp)
    result = (payload or {}).get("result")
    if not isinstance(result, dict):
        return []
    try:
        parsed = json.loads(_result_text(result.get("content")))
    except (TypeError, ValueError):
        return []
    return _parse_web_results(parsed)


async def you_search(query: str, max_results: int = 5) -> str:
    """Search the web with You.com. query: any search query; max_results 1–10."""
    q = (query or "").strip()
    if not q:
        return _payload({"items": [], "error": "empty query"}, "query 不能为空。")
    n = max(1, min(int(max_results or 5), 10))
    try:
        items = _search(q, n)
    except Exception:
        return _payload({"items": [], "silent": True}, "")
    if not items:
        return _payload({"items": [], "silent": True}, "")
    lines = [f"{row['rank']}. {row['title']}" for row in items[:10]]
    text = f"You.com 搜索 “{q}” 共 {len(items)} 条\n" + "\n".join(lines)
    return _payload({"items": items}, text)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "you_search",
        you_search,
        description=(
            "使用 You.com 搜索互联网。query 为搜索词，max_results 为条数（1–10，默认 5）。"
            "未配置 API key 时使用免费匿名端点；配置 YDC_API_KEY 或工具配置 api_key "
            "后使用认证端点。"
        ),
        config_fields=[
            {"name": "api_key", "type": "text", "required": False},
        ],
    )
