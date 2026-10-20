"""Backward-compatible client tool-search imports."""

from octop_harness.middleware.tool_search import (
    ClientToolSearchState,
    ToolSearchInput,
    ToolSearchMiddleware,
    _current_thread_key,
)


class ClientToolSearchMiddleware(ToolSearchMiddleware):
    """Compatibility wrapper for the unified client tool-search middleware."""

    def _request_thread_key(self) -> str | None:
        return _current_thread_key()


__all__ = ["ClientToolSearchMiddleware", "ClientToolSearchState", "ToolSearchInput"]
