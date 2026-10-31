"""Load a plugin or expert catalog from the Octop portal."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import octop.infra.market.http as market_http
from octop.infra.market.errors import PortalMarketError
from octop.infra.market.normalize import sort_recent

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 30.0

_cache_lock = threading.Lock()
_plugin_cache: tuple[float, list[dict[str, Any]]] | None = None
_expert_cache: tuple[float, list[dict[str, Any]]] | None = None


def clear_market_cache() -> None:
    """Drop the in-process catalog cache. Tests call this between cases."""
    global _plugin_cache, _expert_cache
    with _cache_lock:
        _plugin_cache = None
        _expert_cache = None


def cached(scope: str) -> list[dict[str, Any]]:
    """Return one scope, reusing the last successful portal read for a short window."""
    global _plugin_cache, _expert_cache
    now = time.monotonic()
    with _cache_lock:
        slot = _plugin_cache if scope == "plugins" else _expert_cache
        if slot is not None and now - slot[0] < _CACHE_TTL_SECONDS:
            return slot[1]
        items = _load_portal(scope)
        stamped = (now, items)
        if scope == "plugins":
            _plugin_cache = stamped
        else:
            _expert_cache = stamped
        return items


def _load_portal(scope: str) -> list[dict[str, Any]]:
    base = market_http.portal_base()
    if not base:
        raise PortalMarketError("portal url is empty")
    url = f"{base}/api/market/{scope}"
    try:
        payload = market_http.fetch_json(url, limit=market_http.MAX_INDEX_BYTES)
    except PortalMarketError as exc:
        logger.info("portal %s catalog unavailable: %s", scope, exc)
        raise
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise PortalMarketError("portal catalog is invalid")
    data = payload.get("data")
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise PortalMarketError("portal catalog is invalid")
    return sort_recent([item for item in items if isinstance(item, dict)])
