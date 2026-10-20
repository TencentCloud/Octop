"""SSRF guards for agent-initiated outbound fetches (CWE-918).

Used by tools such as ``web_fetch``. User-configured connectors (e.g. MCP
server URLs) are validated separately by the host application and may allow
LAN endpoints on purpose — do not reuse this module for those paths.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.goog",
        "host.docker.internal",
        "gateway.docker.internal",
    }
)
_BLOCKED_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".lan")


class UnsafeAgentFetchUrlError(ValueError):
    """Raised when an agent tool must not fetch the given URL."""


def _ip_is_blocked(ip_str: str) -> bool:
    addr = ipaddress.ip_address(ip_str)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def validate_agent_fetch_url(url: str) -> str:
    """Reject private / loopback / link-local / metadata targets for agent fetches.

    Checks the URL hostname literal and, for non-literal hosts, DNS resolution
    so a public name cannot point at an internal address.
    """
    text = (url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeAgentFetchUrlError(f"url must be http or https, got {parsed.scheme!r}")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeAgentFetchUrlError("url missing hostname")

    if host in _BLOCKED_HOSTNAMES or any(host.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES):
        raise UnsafeAgentFetchUrlError("private or local network addresses are not allowed")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if _ip_is_blocked(host):
            raise UnsafeAgentFetchUrlError("private or local network addresses are not allowed")
        return text

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise UnsafeAgentFetchUrlError(f"cannot resolve hostname {host!r}") from exc
    if not infos:
        raise UnsafeAgentFetchUrlError(f"cannot resolve hostname {host!r}")
    for info in infos:
        sockaddr = info[4]
        ip = sockaddr[0]
        if not isinstance(ip, str):
            continue
        if _ip_is_blocked(ip):
            raise UnsafeAgentFetchUrlError("private or local network addresses are not allowed")
    return text
