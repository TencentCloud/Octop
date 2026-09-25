"""One QCC API key, five fixed MCP resources, one namespaced tool surface."""

from __future__ import annotations

import time
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from octop.infra.utils.ssrf_guard import safe_request

ISSUER = "https://agent.qcc.com"
RESOURCES = {
    name: f"{ISSUER}/mcp/{name}/stream"
    for name in ("company", "risk", "ipr", "operation", "executive")
}

# When a resource actually exposes these names, hide the rest so the model is
# not handed 150+ near-duplicate tools. Unknown catalogs (and unit doubles)
# fall through to the full page.
PREFERRED_TOOL_SUFFIXES: frozenset[str] = frozenset(
    {
        "get_company_profile",
        "get_change_records",
        "get_business_exception",
        "get_patent_info",
        "get_administrative_license",
        "get_executive_positions",
    }
)

_METADATA_TTL_SEC = 600.0
_metadata_ok_until: dict[str, float] = {}


def bearer_token(creds: dict[str, Any]) -> str:
    return str(
        creds.get("api_key") or creds.get("token") or creds.get("access_token") or ""
    ).strip()


def clear_metadata_cache() -> None:
    _metadata_ok_until.clear()


async def _assert_resource_metadata(resource: str) -> str:
    url = RESOURCES[resource]
    now = time.monotonic()
    if _metadata_ok_until.get(resource, 0.0) > now:
        return url
    metadata_response = await safe_request(
        "GET",
        f"{ISSUER}/mcp/.well-known/oauth-protected-resource/{resource}/stream",
        timeout=20.0,
    )
    metadata_response.raise_for_status()
    metadata = metadata_response.json()
    if metadata.get("resource") != url or ISSUER not in metadata.get("authorization_servers", []):
        raise ValueError("QCC resource metadata mismatch")
    _metadata_ok_until[resource] = now + _METADATA_TTL_SEC
    return url


async def request_resource(
    resource: str, token: str, method: str, params: dict[str, Any]
) -> dict[str, Any]:
    """Use the MCP SDK for session initialization, pagination and tool calls.

    No caller-supplied URLs and no credential-bearing redirects are permitted.
    Sessions are short-lived so the stored API key is read on the next call.
    Protected-resource metadata is cached so list/call do not re-handshake.
    """
    url = await _assert_resource_metadata(resource)
    async with (
        httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
            follow_redirects=False,
            trust_env=False,
        ) as client,
        streamable_http_client(url, http_client=client) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        if method == "tools/call":
            result = await session.call_tool(params["name"], params.get("arguments", {}))
            return result.model_dump(mode="json", by_alias=True, exclude_none=True)
        tools: list[dict[str, Any]] = []
        cursor = None
        seen: set[str] = set()
        while True:
            page = await session.list_tools(cursor=cursor)
            tools.extend(
                tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                for tool in page.tools
            )
            cursor = page.nextCursor
            if not cursor:
                return {"tools": tools}
            if cursor in seen:
                raise ValueError("QCC repeated tools cursor")
            seen.add(cursor)


def _tool_suffix(name: str) -> str:
    _, sep, rest = name.partition("__")
    return rest if sep else name


def select_exposed_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matched = [
        tool
        for tool in tools
        if _tool_suffix(str(tool.get("name") or "")) in PREFERRED_TOOL_SUFFIXES
    ]
    return matched or tools


def namespace_tools(resource: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    named = [{**tool, "name": f"{resource}__{tool['name']}"} for tool in result.get("tools", [])]
    return select_exposed_tools(named)


async def probe(token: str) -> dict[str, Any]:
    tools: list[dict[str, Any]] = []
    servers: dict[str, Any] = {}
    for resource in RESOURCES:
        try:
            listed = namespace_tools(
                resource, await request_resource(resource, token, "tools/list", {})
            )
            tools.extend(listed)
            servers[resource] = {"ok": True, "tool_count": len(listed)}
        except Exception:
            servers[resource] = {"ok": False}
    failed = [name for name, result in servers.items() if not result["ok"]]
    return {
        "ok": bool(tools),
        "tools": tools,
        "tool_count": len(tools),
        "servers": servers,
        **({"error": f"QCC MCP probe failed: {', '.join(failed)}"} if failed else {}),
    }
