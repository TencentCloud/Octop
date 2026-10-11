"""Execute or decode Bridge HTTP tunnel frames against the local ASGI app."""

from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from octop.infra.bridge.tunnel_policy import is_tunnel_path_allowed
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

# Hop-by-hop / sensitive headers we never forward into the local ASGI call
# from a remote tunnel initiator (auth is injected as the connection owner).
_DROP_REQUEST_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "connection",
        "transfer-encoding",
        "authorization",
        "cookie",
    }
)
_DROP_RESPONSE_HEADERS = frozenset(
    {
        "content-length",
        "transfer-encoding",
        "connection",
        "content-encoding",
    }
)


def decode_body_b64(payload: dict[str, Any]) -> bytes:
    raw = payload.get("body_b64")
    if not raw:
        return b""
    return base64.b64decode(str(raw))


def encode_tunnel_response(
    *,
    status: int,
    headers: dict[str, str],
    body: bytes,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": status,
        "headers": headers,
        "done": True,
    }
    if body:
        out["body_b64"] = base64.b64encode(body).decode("ascii")
    return out


async def execute_local_http(
    *,
    app: Any,
    method: str,
    path: str,
    query: str = "",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    access_token: str,
) -> dict[str, Any]:
    """Run ``method path`` against the local FastAPI app as ``access_token``."""
    if not is_tunnel_path_allowed(method, path):
        raise OctopError(
            ErrorCode.BRIDGE_REMOTE_UNSUPPORTED,
            "This action is not available through the remote bridge. Manage it on the peer Octop.",
        )
    clean_headers = {
        k: v
        for k, v in (headers or {}).items()
        if k.lower() not in _DROP_REQUEST_HEADERS and v is not None
    }
    clean_headers["authorization"] = f"Bearer {access_token}"
    url = path if path.startswith("/") else f"/{path}"
    if query:
        url = f"{url}?{query}" if "?" not in url else f"{url}&{query}"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://bridge.local",
        timeout=120.0,
    ) as client:
        resp = await client.request(
            method.upper(),
            url,
            headers=clean_headers,
            content=body or None,
        )
    out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in _DROP_RESPONSE_HEADERS}
    return encode_tunnel_response(status=resp.status_code, headers=out_headers, body=resp.content)


def rewrite_agent_path(path: str, *, remote_agent_id: str, bridge_agent_id: str) -> str:
    """Replace a bridge agent id segment with the remote agent id (or reverse)."""
    return path.replace(bridge_agent_id, remote_agent_id)


def build_query_string(params: list[tuple[str, str]]) -> str:
    return urlencode(params)
