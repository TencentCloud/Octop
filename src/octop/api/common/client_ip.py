"""Resolve the client address for security-sensitive decisions.

``X-Forwarded-For`` is caller-supplied, so anything that throttles or rate-limits
on it can be reset by varying one header. The rules here keep that header usable
behind a reverse proxy while refusing to trust it from an arbitrary peer:

* The direct peer address is always trusted.
* ``X-Forwarded-For`` is honoured only when the peer is the loopback interface,
  i.e. a proxy on this host (or in the same pod).
* From that header the **right-most** entry is taken. A trusted proxy appends the
  address it observed, so the right-most value is the one it actually saw; values
  to its left may have been supplied by the client itself.
"""

from __future__ import annotations

import ipaddress
from typing import Any

UNKNOWN_CLIENT = "unknown"


def _peer_address(request: Any) -> str:
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    return host.strip() if isinstance(host, str) and host.strip() else ""


def _is_loopback(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def _forwarded_for_rightmost(request: Any) -> str:
    raw = request.headers.get("x-forwarded-for")
    if not raw:
        return ""
    hops = [part.strip() for part in raw.split(",") if part.strip()]
    return hops[-1] if hops else ""


def resolve_client_ip(request: Any) -> str:
    """The address to key rate limits on.

    Falls back to :data:`UNKNOWN_CLIENT` when the ASGI scope carries no peer
    (e.g. an in-process test client), which collapses those callers into a single
    bucket rather than giving each request a fresh one.
    """
    peer = _peer_address(request)
    if peer and _is_loopback(peer):
        forwarded = _forwarded_for_rightmost(request)
        if forwarded:
            return forwarded
    return peer or UNKNOWN_CLIENT
