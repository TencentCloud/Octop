"""OpenID Connect discovery document helpers."""

from __future__ import annotations

import time
from typing import Any, cast

import httpx

_DISCOVERY_PATH = "/.well-known/openid-configuration"
_CACHE_TTL_SECONDS = 3600


def _normalized_issuer(issuer: str) -> str:
    return issuer.rstrip("/")


def fetch_discovery(issuer: str, *, httpx_client: httpx.Client) -> dict[str, Any]:
    """Fetch an issuer's OpenID Connect discovery document."""
    normalized = _normalized_issuer(issuer)
    response = httpx_client.get(f"{normalized}{_DISCOVERY_PATH}")
    response.raise_for_status()
    discovery = cast(dict[str, Any], response.json())
    doc_issuer = discovery.get("issuer")
    if not isinstance(doc_issuer, str) or _normalized_issuer(doc_issuer) != normalized:
        raise ValueError("OIDC discovery issuer does not match configured issuer")
    return discovery


class DiscoveryCache:
    """In-process cache for OpenID Connect discovery documents."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, dict[str, Any]]] = {}

    def get(self, issuer: str, *, httpx_client: httpx.Client) -> dict[str, Any]:
        normalized_issuer = _normalized_issuer(issuer)
        entry = self._entries.get(normalized_issuer)
        now = time.monotonic()
        if entry is not None and entry[0] > now:
            return entry[1]

        discovery = fetch_discovery(normalized_issuer, httpx_client=httpx_client)
        self._entries[normalized_issuer] = (now + _CACHE_TTL_SECONDS, discovery)
        return discovery

    def invalidate(self, issuer: str) -> None:
        self._entries.pop(_normalized_issuer(issuer), None)
