"""Serialize ACP permission requests that octop-harness lets overlap.

Cursor can ask for several approvals in one turn (two WebSearch calls, for
example). ``ACPHostedClient`` keeps a single future and a single pending
permission. A second ``request_permission`` replaces that future, the resume
resolves the replacement, and the first request waits forever. The agent then
never finishes the turn, so the chat stops on the preamble.
"""

from __future__ import annotations

import asyncio
from typing import Any

_INSTALLED = False
_LOCK_ATTR = "_octop_permission_lock"


def install_acp_permission_queue() -> None:
    """Make overlapping ``request_permission`` calls wait their turn."""
    global _INSTALLED
    if _INSTALLED:
        return
    from octop_harness.acp.client import ACPHostedClient

    original = ACPHostedClient.request_permission

    async def request_permission(
        self: Any,
        options: list[Any],
        session_id: str,
        tool_call: Any,
        **kwargs: Any,
    ) -> Any:
        lock = getattr(self, _LOCK_ATTR, None)
        if lock is None:
            lock = asyncio.Lock()
            setattr(self, _LOCK_ATTR, lock)
        async with lock:
            return await original(self, options, session_id, tool_call, **kwargs)

    ACPHostedClient.request_permission = request_permission  # type: ignore[method-assign]
    _INSTALLED = True


__all__ = ["install_acp_permission_queue"]
