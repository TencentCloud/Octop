"""One QCC grant, five fixed MCP resources, one namespaced tool surface."""

from __future__ import annotations

from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from octop.infra.connectors.oauth.mcp import (
    _ensure_mcp_oauth_url,
    fetch_authorization_metadata,
)
from octop.infra.utils.ssrf_guard import safe_request

ISSUER = "https://agent.qcc.com"
RESOURCES = {
    name: f"{ISSUER}/mcp/{name}/stream"
    for name in ("company", "risk", "ipr", "operation", "executive")
}


def unauthorized(exc: BaseException) -> bool:
    if isinstance(exc, BaseExceptionGroup):
        return any(unauthorized(child) for child in exc.exceptions)
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401


async def request_resource(
    resource: str, token: str, method: str, params: dict[str, Any]
) -> dict[str, Any]:
    """Use the MCP SDK for session initialization, pagination and tool calls.

    No caller-supplied URLs and no credential-bearing redirects are permitted.
    Sessions are short-lived so a rotated grant is used on the next call.
    """
    url = RESOURCES[resource]
    metadata_response = await safe_request(
        "GET",
        f"{ISSUER}/mcp/.well-known/oauth-protected-resource/{resource}/stream",
        timeout=20.0,
    )
    metadata_response.raise_for_status()
    metadata = metadata_response.json()
    if metadata.get("resource") != url or ISSUER not in metadata.get("authorization_servers", []):
        raise ValueError("QCC resource metadata mismatch")
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


def namespace_tools(resource: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    return [{**tool, "name": f"{resource}__{tool['name']}"} for tool in result.get("tools", [])]


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
        "ok": not failed,
        "tools": tools,
        "tool_count": len(tools),
        "servers": servers,
        **({"error": f"QCC MCP probe failed: {', '.join(failed)}"} if failed else {}),
    }


async def revoke(creds: dict[str, Any]) -> None:
    token = str(creds.get("refresh_token") or "")
    if not token:
        return
    metadata = await fetch_authorization_metadata(ISSUER)
    endpoint = await _ensure_mcp_oauth_url(
        str(metadata.get("revocation_endpoint") or ""),
        issuer=ISSUER,
        field="revocation_endpoint",
    )
    response = await safe_request(
        "POST",
        endpoint,
        data={
            "client_id": str(creds.get("oauth_client_id") or ""),
            "token": token,
            "token_type_hint": "refresh_token",
        },
        timeout=20.0,
    )
    response.raise_for_status()
