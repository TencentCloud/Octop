"""MCP tools for managing Octop's custom MCP connectors."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from octop.mcp.client import OctopApiClient

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
CHANGE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
CREATE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)
DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)
EXTERNAL_ACTION = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)


def build_mcp_server(client: OctopApiClient) -> FastMCP:
    """Build the local stdio server around an authenticated Octop API client."""
    mcp = FastMCP(
        "octop-control",
        instructions=(
            "Manage custom MCP connectors in the running Octop instance. Inspect current "
            "state before changing it, ask before deletion, and never reveal stored secrets."
        ),
    )

    @mcp.tool(annotations=READ_ONLY)
    async def octop_get_status() -> dict[str, Any]:
        """Check Octop health and show the authenticated management user."""
        return await client.get_status()

    @mcp.tool(annotations=READ_ONLY)
    async def octop_list_connectors() -> list[dict[str, Any]]:
        """List visible connectors without returning stored credentials or request headers."""
        return await client.list_connectors()

    @mcp.tool(annotations=CREATE)
    async def octop_add_mcp_connector(
        name: str,
        url: str,
        display_name: str | None = None,
        headers: dict[str, str] | None = None,
        enabled: bool = True,
        default_open: bool = False,
        shared: bool = False,
    ) -> dict[str, Any]:
        """Add a Streamable HTTP MCP connector and reload the user's Octop agents.

        The name must contain only letters, digits, underscores, or hyphens. Header values
        may contain credentials; they are stored by Octop but are never returned by this tool.
        """
        return await client.add_http_mcp_connector(
            name=name,
            url=url,
            display_name=display_name,
            headers=headers,
            enabled=enabled,
            default_open=default_open,
            shared=shared,
        )

    @mcp.tool(annotations=CHANGE)
    async def octop_configure_mcp_connector(
        name: str,
        enabled: bool | None = None,
        default_open: bool | None = None,
        shared: bool | None = None,
    ) -> dict[str, Any]:
        """Change enabled, default-open, or sharing flags for one custom MCP connector."""
        if enabled is None and default_open is None and shared is None:
            raise ValueError("at least one connector setting must be provided")
        return await client.patch_mcp_connector(
            name,
            enabled=enabled,
            default_open=default_open,
            shared=shared,
        )

    @mcp.tool(annotations=EXTERNAL_ACTION)
    async def octop_test_mcp_connector(name: str) -> dict[str, Any]:
        """Probe a saved custom MCP connector and return connectivity and tool metadata."""
        return await client.test_mcp_connector(name)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def octop_delete_mcp_connector(name: str) -> dict[str, Any]:
        """Permanently delete one custom MCP connector. Confirm with the user first."""
        return await client.delete_mcp_connector(name)

    return mcp
