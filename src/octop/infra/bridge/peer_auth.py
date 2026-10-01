"""HTTP login against a peer Octop instance."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from octop.infra.errors import ErrorCode, OctopError

# Cloud metadata / link-local — always rejected even for self-hosted LAN peers.
_BLOCKED_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:169.254.0.0/112"),
)


def _host_resolves_blocked(host: str) -> bool:
    hostname = host.strip().strip("[]")
    if not hostname:
        return True
    try:
        # Literal IP — no DNS.
        addr = ipaddress.ip_address(hostname)
        return any(addr in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise OctopError(
            ErrorCode.BRIDGE_PEER_UNREACHABLE,
            f"peer host could not be resolved: {hostname}",
        ) from exc
    for info in infos:
        raw = info[4][0]
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if any(addr in net for net in _BLOCKED_NETWORKS):
            return True
    return False


def normalize_peer_base_url(raw: str) -> str:
    text = (raw or "").strip().rstrip("/")
    if not text:
        raise OctopError(ErrorCode.BRIDGE_PEER_UNREACHABLE, "peer base URL required")
    parsed = urlparse(text if "://" in text else f"http://{text}")
    if parsed.scheme not in {"http", "https"}:
        raise OctopError(ErrorCode.BRIDGE_PEER_UNREACHABLE, "peer URL must be http or https")
    if not parsed.netloc:
        raise OctopError(ErrorCode.BRIDGE_PEER_UNREACHABLE, "peer URL host required")
    host = parsed.hostname or ""
    if _host_resolves_blocked(host):
        raise OctopError(
            ErrorCode.BRIDGE_PEER_UNREACHABLE,
            "peer URL host is not allowed (link-local / metadata addresses blocked)",
        )
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def peer_ws_url(base_url: str, *, token: str) -> str:
    base = normalize_peer_base_url(base_url)
    parsed = urlparse(base)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    root = f"{scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    return f"{root}/api/bridge/ws?token={token}"


async def login_peer(
    *,
    base_url: str,
    username: str,
    password: str,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    """POST /api/auth/login on the peer; return token payload."""
    root = normalize_peer_base_url(base_url)
    url = urljoin(root + "/", "api/auth/login")
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = await client.post(
                url,
                json={"username": username, "password": password},
            )
    except httpx.HTTPError as exc:
        raise OctopError(
            ErrorCode.BRIDGE_PEER_UNREACHABLE,
            f"peer login failed: {exc}",
        ) from exc

    if resp.status_code == 401:
        raise OctopError(ErrorCode.BRIDGE_AUTH_FAILED, "peer rejected credentials")
    if resp.status_code >= 400:
        detail = resp.text[:300]
        raise OctopError(
            ErrorCode.BRIDGE_AUTH_FAILED,
            f"peer login HTTP {resp.status_code}: {detail}",
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise OctopError(ErrorCode.BRIDGE_AUTH_FAILED, "peer login returned non-JSON") from exc
    if not isinstance(data, dict) or not str(data.get("access_token") or "").strip():
        raise OctopError(ErrorCode.BRIDGE_AUTH_FAILED, "peer login missing access_token")
    return data
