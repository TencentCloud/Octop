"""Backward-compatible provider-native tool-search middleware."""

from typing import Literal

from octop_harness.middleware.tool_search import ToolSearchMiddleware


class NativeToolSearchMiddleware(ToolSearchMiddleware):
    """Compatibility wrapper for the unified tool-search middleware."""

    def __init__(
        self,
        *,
        deferred_tools: frozenset[str],
        mcp_tool_names: frozenset[str] | None = None,
        defer_mcp_tools: bool = False,
        fallback: Literal["eager", "error"] = "eager",
    ) -> None:
        super().__init__(
            deferred_tools=deferred_tools,
            mcp_tool_names=mcp_tool_names,
            defer_mcp_tools=defer_mcp_tools,
            mode="native",
            fallback=fallback,
        )


__all__ = ["NativeToolSearchMiddleware"]
