"""Plugin records published on the Octop portal."""

from __future__ import annotations

from typing import Any

from octop.infra.market.normalize import valid_id
from octop.infra.market.source import cached


def list_market_plugins() -> list[dict[str, Any]]:
    """Return portal plugin records, newest release of each id."""
    return cached("plugins")


def get_market_plugin(plugin_id: str) -> dict[str, Any] | None:
    if not valid_id(plugin_id):
        return None
    for item in cached("plugins"):
        if item.get("id") == plugin_id:
            return item
    return None
