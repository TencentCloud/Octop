"""Run the Octop connector-management MCP server."""

from __future__ import annotations

import logging

import click


@click.command("mcp")
@click.option("--user", "as_user", default=None, help="Octop user identity for API permissions.")
@click.option(
    "--base-url",
    default=None,
    envvar="OCTOP_MCP_BASE_URL",
    help="Running Octop URL (default: local configured port).",
)
@click.option("--debug", is_flag=True, default=False, help="Enable MCP logs on stderr.")
def mcp_cmd(as_user: str | None, base_url: str | None, debug: bool) -> None:
    """Expose Octop connector management over MCP stdio."""
    from octop.cli.support.ctx import resolve_user
    from octop.cli.support.mcp_auth import (
        issue_local_access_token,
        resolve_mcp_base_url,
        resolve_mcp_username,
    )
    from octop.mcp.client import OctopApiClient
    from octop.mcp.server import build_mcp_server

    try:
        username = resolve_mcp_username(resolve_user(as_user))
        token = issue_local_access_token(username)
        url = resolve_mcp_base_url(base_url)
    except (OSError, RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    server = build_mcp_server(OctopApiClient(base_url=url, token=token))
    try:
        server.run(transport="stdio")
    except KeyboardInterrupt:
        raise SystemExit(0) from None
