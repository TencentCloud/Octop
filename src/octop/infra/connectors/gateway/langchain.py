"""LangChain tool factory for in-process gateway MCP fallback."""

from __future__ import annotations

import json
from typing import Any

from harness_agent.mcp import mcp_args_model, sanitize_llm_tool_name

from octop.infra.connectors.catalog import ConnectorCatalogEntry
from octop.infra.connectors.gateway.protocol import handle_mcp_request
from octop.infra.connectors.gateway.registry import mcp_tools_for_kind


def build_gateway_langchain_tools(
    *,
    entry: Any,
    instance_id: str,
    mcp_server_name: str,
    creds: dict[str, Any],
) -> list[Any]:
    """In-process LangChain tools when harness HTTP MCP load misses gateway servers."""
    from langchain_core.tools import StructuredTool

    del instance_id
    if not isinstance(entry, ConnectorCatalogEntry) or entry.mcp_mode != "gateway":
        return []
    out: list[Any] = []

    def _tool_fn(kind: str, tool_name: str) -> Any:
        def _run(**kwargs: Any) -> str:
            # Null stripping for args_schema happens in harness mcp_args_model.
            cleaned = {k: v for k, v in kwargs.items() if v is not None}
            resp = handle_mcp_request(
                kind=kind,
                creds=creds,
                body={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": cleaned},
                },
            )
            if not isinstance(resp, dict):
                return "gateway error"
            if resp.get("error"):
                err = resp.get("error") or {}
                return str(err.get("message") or err)
            result = resp.get("result") or {}
            if result.get("isError"):
                content = result.get("content") or []
                if content and isinstance(content[0], dict):
                    return str(content[0].get("text") or "tool error")
                return "tool error"
            content = result.get("content") or []
            if content and isinstance(content[0], dict) and content[0].get("text"):
                return str(content[0]["text"])
            return json.dumps(result, ensure_ascii=False)

        return _run

    for tool_def in mcp_tools_for_kind(entry.kind):
        name = str(tool_def.get("name") or "").strip()
        if not name:
            continue
        input_schema = tool_def.get("inputSchema")
        if not isinstance(input_schema, dict):
            input_schema = {"type": "object", "properties": {}}
        lc_name = sanitize_llm_tool_name(f"{mcp_server_name}_{name}")
        out.append(
            StructuredTool.from_function(
                func=_tool_fn(entry.kind, name),
                name=lc_name,
                description=str(tool_def.get("description") or name),
                args_schema=mcp_args_model(lc_name, input_schema),
            )
        )
    return out
