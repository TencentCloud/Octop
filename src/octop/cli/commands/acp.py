"""`octop acp` — run Octop agent as an ACP server over stdio."""

from __future__ import annotations

import asyncio
import logging

import click


async def _run_acp_server(*, agent_id: str | None, debug: bool) -> None:
    from octop.cli.support.state import default_state_path, load
    from octop.infra.server import OctopServer

    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")

    srv = OctopServer()
    await srv.start()
    assert srv.app_runtime is not None
    registry = srv.app_runtime.agent_registry

    aid = agent_id
    if not aid:
        state = load(default_state_path())
        aid = state.default_agent
    if not aid:
        rows = registry.list_rows()
        if not rows:
            raise click.ClickException(
                "no agent found; create one in the dashboard or pass --agent",
            )
        aid = rows[0].agent_id

    try:
        harness = registry.get_agent(aid)
    except Exception as exc:
        raise click.ClickException(f"agent {aid!r} is not running: {exc}") from exc

    from octop_harness.acp.server import run_harness_acp_server

    try:
        await run_harness_acp_server(harness, agent_id=aid)
    finally:
        await srv.stop()


@click.command("acp")
@click.option(
    "--agent", "agent_id", default=None, help="Agent ID (defaults to CLI state / first agent)"
)
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging to stderr")
def acp_cmd(agent_id: str | None, debug: bool) -> None:
    """Start Octop as an ACP agent (stdio) for IDE clients (Zed, OpenCode, …)."""
    from octop.cli.support.ctx import resolve_agent

    aid = resolve_agent(agent_id)
    try:
        asyncio.run(_run_acp_server(agent_id=aid, debug=debug))
    except click.ClickException:
        raise
    except KeyboardInterrupt:
        raise SystemExit(0) from None
