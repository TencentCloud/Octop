"""Helpers to propagate ``~/.octop/env`` changes to a running server."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from octop.infra.utils.env_file import search_env_changed

logger = logging.getLogger(__name__)


def reload_agents_after_env_change(
    server: Any,
    previous: Mapping[str, str],
    new: Mapping[str, str],
) -> None:
    """Sync server-side caches after ``~/.octop/env`` was rewritten.

    Invalidates the MCP tool cache and reloads every agent in the background
    when a web-search key changed (search tools are mounted at agent build
    time). Non-search keys need no reload.
    """
    runtime = getattr(server, "app_runtime", None)
    registry = getattr(runtime, "agent_registry", None) if runtime is not None else None
    if registry is None:
        return
    invalidate = getattr(registry, "invalidate_mcp_tool_cache", None)
    if callable(invalidate):
        invalidate()
    if not search_env_changed(previous, new):
        return
    reload_all = getattr(registry, "reload_all", None)
    if not callable(reload_all):
        return

    async def _reload() -> None:
        try:
            await reload_all()
        except Exception:
            logger.exception("background agent reload after search env change failed")

    asyncio.create_task(_reload(), name="reload-agents-search-env")


__all__ = ["reload_agents_after_env_change"]
