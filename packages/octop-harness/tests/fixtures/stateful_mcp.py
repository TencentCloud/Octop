"""Real fake MCP subprocess; no model or network required."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

server = FastMCP("stateful-test")
draft: dict[str, str] = {}


@server.tool()
def collect(title: str) -> str:
    """Save a process-local draft."""
    draft["title"] = title
    return "collected"


@server.tool()
def confirm() -> dict[str, str]:
    """Confirm the saved draft."""
    return {"title": draft["title"]}


@server.resource("memory://brief")
def brief() -> str:
    return draft["title"]


if __name__ == "__main__":
    server.run(transport="stdio")
