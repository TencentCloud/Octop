"""One-tool MCP server so an external ACP agent can search Octop knowledge bases."""

from __future__ import annotations

from typing import Any

from octop.infra.knowledge.params import MAX_RETRIEVAL_K, MIN_RETRIEVAL_K
from octop.infra.knowledge.retrieve import retrieve_context
from octop.infra.knowledge.tools import format_search_knowledge_description

_PROTOCOL = "2024-11-05"


def knowledge_tool_schema(catalog: list[dict[str, str]]) -> dict[str, Any]:
    """Tool definition advertised by ``tools/list``."""
    return {
        "name": "search_knowledge",
        "description": format_search_knowledge_description(catalog),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Focused search string: key terms, names, and synonyms. Not a chat reply."
                    ),
                },
                "k": {
                    "type": "integer",
                    "description": (
                        "Maximum passages to return. Omit to use the knowledge base settings."
                    ),
                    "minimum": MIN_RETRIEVAL_K,
                    "maximum": MAX_RETRIEVAL_K,
                },
            },
            "required": ["query"],
        },
    }


def _ok(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    if req_id is None:
        return {}
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _arguments(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    raw = params.get("arguments") or {}
    if not isinstance(raw, dict):
        return {}
    nested = raw.get("kwargs")
    if nested is not None and set(raw.keys()) == {"kwargs"} and isinstance(nested, dict):
        return nested
    return raw


def _passage_limit(raw: Any) -> int | None:
    try:
        k = int(raw)
    except (TypeError, ValueError):
        return None
    return min(MAX_RETRIEVAL_K, max(MIN_RETRIEVAL_K, k))


async def handle_knowledge_mcp(
    body: dict[str, Any],
    *,
    user_id: int,
    is_admin: bool,
    knowledge_base_ids: list[str],
    locale: str,
    catalog: list[dict[str, str]],
    services: Any,
) -> dict[str, Any]:
    """Answer one JSON-RPC request. An empty dict means the caller should return 202."""
    method = str(body.get("method") or "")
    req_id = body.get("id")
    params = body.get("params") or {}

    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": _PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "octop-knowledge", "version": "0.1.0"},
            },
        )
    if method == "notifications/initialized":
        return {}
    if method == "tools/list":
        return _ok(req_id, {"tools": [knowledge_tool_schema(catalog)]})
    if method == "ping":
        return _ok(req_id, {})
    if method != "tools/call":
        return _err(req_id, -32601, f"Method not found: {method}")

    arguments = _arguments(params)
    name = str(params.get("name") or "") if isinstance(params, dict) else ""
    if name != "search_knowledge":
        return _ok(
            req_id,
            {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True},
        )
    query = str(arguments.get("query") or "").strip()
    if not query:
        return _ok(
            req_id,
            {
                "content": [{"type": "text", "text": "query is required."}],
                "isError": True,
            },
        )
    if not knowledge_base_ids:
        text = "No knowledge bases selected for this turn."
    else:
        text = await retrieve_context(
            services,
            user_id=user_id,
            is_admin=is_admin,
            query=query,
            knowledge_base_ids=knowledge_base_ids,
            k=_passage_limit(arguments.get("k")),
            locale=locale,
        )
        if not text:
            text = "No relevant passages found."
    return _ok(req_id, {"content": [{"type": "text", "text": text}], "isError": False})
