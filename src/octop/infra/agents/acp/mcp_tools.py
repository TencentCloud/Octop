"""JSON-RPC helpers for Octop loopback MCP servers."""

from __future__ import annotations

import asyncio
import json
from typing import Any

_PROTOCOL = "2024-11-05"


def ok(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    if req_id is None:
        return {}
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def err(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def arguments(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    raw = params.get("arguments") or {}
    if not isinstance(raw, dict):
        return {}
    nested = raw.get("kwargs")
    if nested is not None and set(raw.keys()) == {"kwargs"} and isinstance(nested, dict):
        return nested
    return raw


def text_result(req_id: Any, text: str, *, failed: bool = False) -> dict[str, Any]:
    return ok(req_id, {"content": [{"type": "text", "text": text}], "isError": failed})


def tool_card(tool: Any) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": {}}
    model = getattr(tool, "args_schema", None)
    if model is not None and hasattr(model, "model_json_schema"):
        raw = model.model_json_schema()
        if isinstance(raw, dict):
            schema = dict(raw)
            schema.pop("title", None)
    return {
        "name": str(getattr(tool, "name", "") or "tool"),
        "description": str(getattr(tool, "description", "") or ""),
        "inputSchema": schema,
    }


def _invoke_sync(tool: Any, payload: dict[str, Any], config: dict[str, Any]) -> Any:
    from langchain_core.runnables.config import var_child_runnable_config

    token = var_child_runnable_config.set({"configurable": config})
    try:
        return tool.invoke(payload)
    finally:
        var_child_runnable_config.reset(token)


async def invoke_tool(tool: Any, payload: dict[str, Any], config: dict[str, Any]) -> str:
    """Run one structured tool. Cron and plugins read ``get_config()`` from this config."""
    try:
        if getattr(tool, "coroutine", None) is not None:
            from langchain_core.runnables.config import var_child_runnable_config

            token = var_child_runnable_config.set({"configurable": config})
            try:
                result = await tool.ainvoke(payload)
            finally:
                var_child_runnable_config.reset(token)
        else:
            result = await asyncio.to_thread(_invoke_sync, tool, payload, config)
    except Exception as exc:
        name = str(getattr(tool, "name", "") or "tool")
        return f"{name} failed: {exc}"
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


async def dispatch(
    body: dict[str, Any],
    *,
    server_name: str,
    tools: list[Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Answer one JSON-RPC request. An empty dict means the caller should return 202."""
    method = str(body.get("method") or "")
    req_id = body.get("id")
    params = body.get("params") or {}
    if method == "initialize":
        return ok(
            req_id,
            {
                "protocolVersion": _PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": server_name, "version": "0.1.0"},
            },
        )
    if method == "notifications/initialized":
        return {}
    if method == "tools/list":
        return ok(req_id, {"tools": [tool_card(tool) for tool in tools]})
    if method == "ping":
        return ok(req_id, {})
    if method != "tools/call":
        return err(req_id, -32601, f"Method not found: {method}")

    name = str(params.get("name") or "") if isinstance(params, dict) else ""
    tool = next((item for item in tools if getattr(item, "name", None) == name), None)
    if tool is None:
        return text_result(req_id, f"Unknown tool: {name}", failed=True)
    text = await invoke_tool(tool, arguments(params), config or {})
    failed = text.startswith(f"{name} failed:")
    return text_result(req_id, text, failed=failed)
