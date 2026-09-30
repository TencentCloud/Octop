"""Proxy HTTP requests for ``bridge:{connection_id}:{agent_id}`` agent paths."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from octop.infra.bridge.ids import (
    BridgeAgentRef,
    parse_bridge_agent_id,
    restore_peer_path_ids,
    rewrite_tunneled_json,
)
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

_INSTALL_ATTR = "_octop_bridge_proxy_installed"

# /api/agents/bridge:{cid}:{aid} or percent-encoded bridge%3A…
_BRIDGE_AGENT_PATH = re.compile(
    r"^/api/agents/(bridge(?::|%3[Aa])[^/]+)(/.*)?$",
)
_BRIDGE_PLUGIN_AGENT_PATH = re.compile(
    r"^/api/plugins/agents/(bridge(?::|%3[Aa])[^/]+)(/.*)?$",
)


@dataclass(frozen=True)
class TunnelTarget:
    """Resolved hub → peer hop for a Bridge shadow request."""

    ref: BridgeAgentRef
    agent_token: str
    remote_path: str
    """Path suffix after the agent id for /api/agents/… shadows (local short-circuit)."""
    agent_rest: str = ""


def _is_header_tunneled_path(path: str) -> bool:
    raw = (path or "").split("?", 1)[0].strip() or "/"
    if len(raw) > 1:
        raw = raw.rstrip("/")
    if raw == "/api/mbti" or raw.startswith("/api/mbti/"):
        return True
    if raw == "/api/subagent-catalog" or raw.startswith("/api/subagent-catalog/"):
        return True
    if raw == "/api/cron/settings":
        return True
    if raw == "/api/connector-instances":
        return True
    if raw in {
        "/api/providers/resolved",
        "/api/providers/active-model",
        "/api/knowledge-bases",
        "/api/knowledge-bases/capability",
        "/api/browser/env-status",
        "/api/browser/harness-sessions",
    }:
        return True
    return raw == "/api/acp" or raw.startswith("/api/acp/")


def _restore_shadow_in_rest(rest: str, *, token: str, ref: BridgeAgentRef) -> str:
    """Undo a stale hub thread/session segment that embedded the shadow id."""
    out = restore_peer_path_ids(
        rest,
        bridge_agent_id=ref.agent_id,
        remote_agent_id=ref.remote_agent_id,
    )
    if token != ref.agent_id:
        out = restore_peer_path_ids(
            out,
            bridge_agent_id=token,
            remote_agent_id=ref.remote_agent_id,
        )
    encoded = quote(ref.agent_id, safe="")
    if encoded != ref.agent_id:
        out = restore_peer_path_ids(
            out,
            bridge_agent_id=encoded,
            remote_agent_id=ref.remote_agent_id,
        )
    return out


def resolve_tunnel_target(
    path: str,
    agent_header: str | None = None,
) -> TunnelTarget | None:
    """Return a tunnel target when ``path`` / ``X-Octop-Agent-Id`` names a Bridge agent."""
    raw = (path or "").split("?", 1)[0] or "/"

    match = _BRIDGE_AGENT_PATH.match(raw)
    if match is not None:
        token = unquote(match.group(1))
        ref = parse_bridge_agent_id(token)
        if ref is not None:
            rest = _restore_shadow_in_rest(
                match.group(2) or "",
                token=token,
                ref=ref,
            )
            return TunnelTarget(
                ref=ref,
                agent_token=token,
                remote_path=f"/api/agents/{ref.remote_agent_id}{rest}",
                agent_rest=rest,
            )

    match = _BRIDGE_PLUGIN_AGENT_PATH.match(raw)
    if match is not None:
        token = unquote(match.group(1))
        ref = parse_bridge_agent_id(token)
        if ref is not None:
            rest = _restore_shadow_in_rest(
                match.group(2) or "",
                token=token,
                ref=ref,
            )
            return TunnelTarget(
                ref=ref,
                agent_token=token,
                remote_path=f"/api/plugins/agents/{ref.remote_agent_id}{rest}",
            )

    header = unquote((agent_header or "").strip())
    ref = parse_bridge_agent_id(header)
    if ref is None or not _is_header_tunneled_path(raw):
        return None
    return TunnelTarget(
        ref=ref,
        agent_token=ref.agent_id,
        remote_path=raw,
    )


def _local_bridge_shadow_response(
    *,
    method: str,
    rest: str,
) -> JSONResponse | None:
    """Answer hub-only poll paths without tunneling to the peer.

    ``/status`` is tunneled (peer allowlist) so the hub sees real harness state.
    ``history-migration`` is a local-archive concern and must not hop the bridge.
    """
    verb = (method or "GET").upper()
    path = rest or ""

    if path.startswith("/history-migration"):
        if verb == "GET" and path == "/history-migration/status":
            return JSONResponse(
                {
                    "remaining": 0,
                    "pending": 0,
                    "queued": 0,
                    "running": 0,
                    "failed": 0,
                    "processing": False,
                    "agent_busy": False,
                    "can_start": False,
                }
            )
        raise OctopError(
            ErrorCode.BRIDGE_REMOTE_UNSUPPORTED,
            "This action is not available through the remote bridge. Manage it on the peer Octop.",
        )

    return None


def _forward_headers(request: Request, remote_agent_id: str) -> dict[str, str]:
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower()
        not in {
            "host",
            "content-length",
            "authorization",
            "connection",
            "transfer-encoding",
        }
    }
    rewritten = False
    for key in list(headers):
        if key.lower() == "x-octop-agent-id":
            headers[key] = remote_agent_id
            rewritten = True
            break
    if not rewritten:
        headers["X-Octop-Agent-Id"] = remote_agent_id
    return headers


def install(app: Any, server: Any) -> None:
    if getattr(app, _INSTALL_ATTR, False):
        return
    setattr(app, _INSTALL_ATTR, True)

    @app.middleware("http")  # type: ignore[untyped-decorator]
    async def _bridge_proxy(
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        path = request.url.path
        target = resolve_tunnel_target(
            path,
            request.headers.get("x-octop-agent-id"),
        )
        if target is None:
            return await call_next(request)
        # WebSocket upgrades are handled by the chat/bridge routers.
        if (request.headers.get("connection") or "").lower() == "upgrade":
            return await call_next(request)

        user = getattr(request.state, "octop_user", None)
        rt = getattr(server, "app_runtime", None)
        mgr = getattr(rt, "bridge_manager", None) if rt is not None else None
        if user is None or mgr is None:
            return await call_next(request)

        try:
            local = (
                _local_bridge_shadow_response(
                    method=request.method,
                    rest=target.agent_rest,
                )
                if target.agent_rest
                else None
            )
        except OctopError as exc:
            from octop.infra.utils.locale import resolve_request_locale

            locale = resolve_request_locale(request)
            return JSONResponse(
                status_code=exc.status,
                content=exc.to_envelope(locale=locale),
            )
        if local is not None:
            return local

        body = await request.body()
        headers = _forward_headers(request, target.ref.remote_agent_id)
        try:
            peer_resp = await mgr.tunnel_http(
                connection_id=target.ref.connection_id,
                owner_user_id=int(user.id),
                method=request.method,
                path=target.remote_path,
                query=request.url.query,
                headers=headers,
                body=body or None,
            )
        except OctopError as exc:
            from octop.infra.utils.locale import resolve_request_locale

            locale = resolve_request_locale(request)
            return JSONResponse(
                status_code=exc.status,
                content=exc.to_envelope(locale=locale),
            )
        except Exception:
            logger.exception("bridge proxy failed path=%s", path)
            return JSONResponse(
                status_code=502,
                content={
                    "error": {"code": "BRIDGE_TUNNEL_FAILED", "message": "bridge proxy failed"}
                },
            )

        content = peer_resp.content
        media = peer_resp.headers.get("content-type", "")
        if "json" in media:
            try:
                data = json.loads(content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                data = None
            if data is not None:
                rewritten = rewrite_tunneled_json(
                    data,
                    remote_agent_id=target.ref.remote_agent_id,
                    bridge_agent_id=target.ref.agent_id,
                )
                content = json.dumps(rewritten, ensure_ascii=False).encode("utf-8")

        out_headers = {
            k: v
            for k, v in peer_resp.headers.items()
            if k.lower()
            not in {
                "content-length",
                "transfer-encoding",
                "connection",
                "content-encoding",
            }
        }
        return Response(
            content=content,
            status_code=peer_resp.status_code,
            headers=out_headers,
            media_type=peer_resp.headers.get("content-type"),
        )
