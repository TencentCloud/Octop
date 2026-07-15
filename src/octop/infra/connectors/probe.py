"""Connector credential probe — validate connectivity and list tools."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from mcp.shared.exceptions import McpError

from octop.config import OctopConfig
from octop.infra.connectors.builder import (
    build_http_mcp_spec,
    normalize_weiyun_mcp_token,
    validate_create_credentials,
)
from octop.infra.connectors.catalog import ConnectorCatalogEntry, get_catalog_entry
from octop.infra.connectors.gateway.protocol import handle_mcp_request
from octop.infra.connectors.gateway.registry import probe_gateway_credentials
from octop.infra.utils.ssrf_guard import UnsafeOutboundUrl, safe_request

logger = logging.getLogger(__name__)


def normalize_tools(raw: list[Any] | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        out.append(
            {
                "name": name,
                "description": str(item.get("description") or ""),
            }
        )
    return out


def http_error_message(response: httpx.Response) -> str | None:
    if response.status_code < 400:
        return None
    try:
        body = response.json()
        if isinstance(body, dict):
            for key in ("show_msg", "message", "desc", "detail", "error"):
                val = body.get(key)
                if val and str(val).strip() and not str(val).strip().isdigit():
                    return str(val).strip()
    except Exception:
        pass
    if response.status_code == 401:
        return "认证失败，请检查 Token 或授权码"
    return f"HTTP {response.status_code}"


def static_probe_tools(kind: str) -> list[dict[str, str]]:
    if kind == "tencent-weiyun":
        entry = get_catalog_entry(kind)
        if entry and entry.allowed_tools:
            return [{"name": name, "description": ""} for name in entry.allowed_tools]
    return []


async def prepare_probe_credentials(
    kind: str,
    credentials: dict[str, Any],
    *,
    full_prepare: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Like credential creation but allows empty token for remote connectivity probes."""
    entry = get_catalog_entry(kind)
    if entry is None:
        raise ValueError(f"unknown connector kind: {kind}")
    if entry.kind == "tencent-weiyun" and entry.auth_kind == "personal_token":
        raw = str(credentials.get("token") or credentials.get("access_token") or "").strip()
        token = normalize_weiyun_mcp_token(raw)
        return {"token": token} if token else {}
    if entry.kind == "youdao-note" and entry.auth_kind == "personal_token":
        api_key = str(
            credentials.get("token")
            or credentials.get("api_key")
            or credentials.get("access_token")
            or ""
        ).strip()
        return {"token": api_key} if api_key else {}
    if full_prepare is not None:
        return await full_prepare(kind, credentials)
    return validate_create_credentials(kind, credentials)


def _probe_mcp_http_error(exc: httpx.HTTPStatusError, *, kind: str) -> dict[str, Any]:
    """Map an HTTP status error from a remote MCP probe to a clear result.

    ``401``/``403`` are definitive auth rejections (bad key), everything else
    (5xx, 429, network proxy errors) is treated as a connection/upstream
    problem so callers can distinguish "key is wrong" from "can't reach host".
    """
    status = exc.response.status_code
    if status in (401, 403):
        if kind == "youdao-note":
            return _probe_youdao_note_http_error(exc)
        err = http_error_message(exc.response)
        return {
            "ok": False,
            "error_type": "auth",
            "error": err or str(exc),
            "status_code": status,
        }
    err = http_error_message(exc.response)
    return {
        "ok": False,
        "error_type": "connection",
        "error": err or str(exc),
        "status_code": status,
    }


def _probe_mcp_mcp_error(exc: McpError, *, kind: str) -> dict[str, Any]:
    """Map an MCP-level error (e.g. server closing the initialize stream).

    ``Connection closed`` means the upstream dropped the SSE stream — a
    transport/network issue (proxy timeout, geo/network restriction), NOT an
    auth rejection. The credential may still be perfectly valid; report it as
    a connection problem so it is not mistaken for a bad key.
    """
    msg = str(exc).lower()
    if "connection closed" in msg or "connection" in msg:
        return {
            "ok": False,
            "error_type": "connection",
            "error": "与上游 MCP 服务的连接被中断（可能是网络/代理/地域限制），并非密钥无效",
        }
    if kind == "youdao-note":
        return {
            "ok": False,
            "error_type": "auth",
            "error": "API Key 无效或服务暂时不可用，请检查 Key 或在 MCP 平台重新创建",
        }
    return {"ok": False, "error_type": "connection", "error": str(exc)}


def _unwrap_probe_exception_group(exc: BaseExceptionGroup, *, kind: str) -> dict[str, Any] | None:
    """Unwrap a nested TaskGroup exception group to a concrete probe result.

    The mcp SSE client raises nested exception groups whose members are
    transport-level errors. Surface the most actionable one: HTTP status
    errors (auth/permission) and MCP errors (server rejected initialize).
    """
    for sub in exc.exceptions:
        if isinstance(sub, httpx.HTTPStatusError):
            return _probe_mcp_http_error(sub, kind=kind)
        if isinstance(sub, McpError):
            return _probe_mcp_mcp_error(sub, kind=kind)
    for sub in exc.exceptions:
        if isinstance(sub, BaseExceptionGroup):
            nested = _unwrap_probe_exception_group(sub, kind=kind)
            if nested is not None:
                return nested
    return None


async def _probe_mcp_sse(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    kind: str,
) -> dict[str, Any]:
    """Probe a remote MCP server over SSE transport.

    A single retry tolerates transient connection drops (e.g. a proxy or the
    upstream closing the SSE stream on the first ``initialize``). Auth
    rejections (HTTP 401/403) are definitive and returned immediately so a
    bad key is never masked by a retry.
    """
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    for attempt in range(2):
        result: dict[str, Any] | None = None
        try:
            async with (
                sse_client(url, headers or {}, timeout=20, sse_read_timeout=20) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                listed = await session.list_tools()
                tools = normalize_tools(
                    [{"name": t.name, "description": t.description or ""} for t in listed.tools]
                )
                return {"ok": True, "tool_count": len(tools), "tools": tools}
        except httpx.HTTPStatusError as exc:
            result = _probe_mcp_http_error(exc, kind=kind)
            if result.get("error_type") != "connection" or attempt > 0:
                return result
            logger.warning("%s SSE probe connection failure, retrying: %s", kind, exc)
            continue
        except McpError as exc:
            result = _probe_mcp_mcp_error(exc, kind=kind)
            if result.get("error_type") != "connection" or attempt > 0:
                return result
            logger.warning("%s SSE probe connection failure, retrying: %s", kind, exc)
            continue
        except BaseExceptionGroup as exc:
            result = _unwrap_probe_exception_group(exc, kind=kind)
            if result is not None:
                if result.get("error_type") != "connection" or attempt > 0:
                    return result
                logger.warning("%s SSE probe connection failure, retrying: %s", kind, exc)
                continue
            if attempt == 0:
                logger.warning("%s SSE probe transient failure, retrying: %s", kind, exc)
                continue
            logger.exception("%s SSE probe failed", kind)
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            if attempt == 0:
                logger.warning("%s SSE probe transient failure, retrying: %s", kind, exc)
                continue
            logger.exception("%s SSE probe failed", kind)
            return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "SSE probe failed after retry"}


async def probe_youdao_note(api_key: str) -> dict[str, Any]:
    """Probe Youdao Note via MCP SSE (streamable HTTP POST is not supported)."""
    return await _probe_mcp_sse(
        "https://open.mail.163.com/api/ynote/mcp/sse",
        {"x-api-key": api_key},
        kind="youdao-note",
    )


def _probe_youdao_note_http_error(exc: httpx.HTTPStatusError) -> dict[str, Any]:
    if exc.response.status_code == 401:
        try:
            body = exc.response.json()
            if isinstance(body, dict) and body.get("desc"):
                return {
                    "ok": False,
                    "error_type": "auth",
                    "error": str(body["desc"]),
                    "status_code": 401,
                }
        except Exception:
            pass
        return {
            "ok": False,
            "error_type": "auth",
            "error": "API Key 无效，请检查或在 MCP 平台重新创建",
            "status_code": 401,
        }
    err = http_error_message(exc.response)
    return {
        "ok": False,
        "error_type": "connection",
        "error": err or str(exc),
        "status_code": exc.response.status_code,
    }


_STREAMABLE_HTTP_PROBE_KINDS = frozenset({"notion"})

# Connectors whose tool list is known statically (from the catalog
# ``allowed_tools``); a failing ``tools/list`` during probe is tolerated for
# these because :func:`static_probe_tools` supplies the fallback list.
_REMOTE_STATIC_TOOL_KINDS = frozenset({"tencent-weiyun"})


async def probe_streamable_http_mcp(
    url: str,
    headers: dict[str, str],
    *,
    kind: str,
) -> dict[str, Any]:
    """Probe Notion/Figma-style remote MCP via Streamable HTTP (session + SSE)."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    try:
        async with (
            streamablehttp_client(url, headers=headers, timeout=20, sse_read_timeout=20) as (
                read,
                write,
                _get_session_id,
            ),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            listed = await session.list_tools()
            tools = normalize_tools(
                [{"name": t.name, "description": t.description or ""} for t in listed.tools]
            )
            return {"ok": True, "tool_count": len(tools), "tools": tools}
    except httpx.HTTPStatusError as exc:
        return _probe_mcp_http_error(exc, kind=kind)
    except McpError as exc:
        return _probe_mcp_mcp_error(exc, kind=kind)
    except BaseExceptionGroup as exc:
        result = _unwrap_probe_exception_group(exc, kind=kind)
        if result is not None:
            return result
        logger.exception("streamable HTTP MCP probe failed for %s", kind)
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("streamable HTTP MCP probe failed for %s", kind)
        return {"ok": False, "error": str(exc)}


async def probe_connector(
    entry: ConnectorCatalogEntry,
    cred_payload: dict[str, Any],
    *,
    instance_id: str,
    config: OctopConfig,
) -> dict[str, Any]:
    if entry.mcp_mode == "gateway":
        try:
            await asyncio.to_thread(probe_gateway_credentials, entry.kind, cred_payload)
        except Exception as exc:
            logger.info("gateway credential probe failed for %s: %s", entry.kind, exc)
            return {"ok": False, "error": str(exc)}
        resp = handle_mcp_request(
            kind=entry.kind,
            creds=cred_payload,
            body={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        if isinstance(resp, dict) and resp.get("error"):
            msg = str((resp.get("error") or {}).get("message") or "gateway error")
            return {"ok": False, "error": msg}
        tools = normalize_tools(
            (resp.get("result") or {}).get("tools") if isinstance(resp, dict) else None
        )
        return {"ok": True, "tool_count": len(tools), "tools": tools}

    if entry.kind == "youdao-note":
        api_key = str(
            cred_payload.get("token")
            or cred_payload.get("api_key")
            or cred_payload.get("access_token")
            or ""
        ).strip()
        if not api_key:
            return {"ok": False, "error": "请填写 API Key"}
        return await probe_youdao_note(api_key)

    spec = build_http_mcp_spec(
        entry=entry,
        instance_id=instance_id,
        creds=cred_payload,
        config=config,
    )
    headers = dict(spec.get("headers") or {})
    url = str(spec["url"])

    if entry.kind in _STREAMABLE_HTTP_PROBE_KINDS:
        return await probe_streamable_http_mcp(url, headers, kind=entry.kind)

    try:
        r = await safe_request(
            "POST",
            url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "octop", "version": "0.1"},
                },
            },
            headers=headers,
            timeout=20.0,
        )
    except UnsafeOutboundUrl as exc:
        logger.warning("connector probe blocked (SSRF guard): %s", exc)
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("connector probe failed for %s", entry.kind)
        return {"ok": False, "error": str(exc)}

    err = http_error_message(r)
    if err:
        return {"ok": False, "error": err, "status_code": r.status_code}
    if r.status_code >= 500:
        return {
            "ok": False,
            "error": f"远端服务错误 HTTP {r.status_code}",
            "status_code": r.status_code,
        }

    probed_tools: list[dict[str, str]] = []
    try:
        r2 = await safe_request(
            "POST",
            url,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
            headers=headers,
            timeout=20.0,
        )
        list_err = http_error_message(r2)
        if list_err and entry.kind not in _REMOTE_STATIC_TOOL_KINDS:
            return {"ok": False, "error": list_err, "status_code": r2.status_code}
        if r2.status_code < 400:
            body = r2.json()
            if isinstance(body, dict):
                probed_tools = normalize_tools((body.get("result") or {}).get("tools"))
    except Exception:
        logger.debug("connector tools/list probe skipped for %s", entry.kind)

    if not probed_tools:
        probed_tools = static_probe_tools(entry.kind)

    return {
        "ok": True,
        "status_code": r.status_code,
        "tool_count": len(probed_tools),
        "tools": probed_tools,
    }
