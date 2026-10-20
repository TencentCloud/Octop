"""The `octop-harness agent` command group — manage agent profiles."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from octop_harness.cli.agents.manager import CliAgentManager
from octop_harness.cli.agents.profile import AgentProfile
from octop_harness.cli.config.paths import CliPaths

console = Console()


def _get_manager() -> CliAgentManager:
    paths = CliPaths(project_dir=Path.cwd())
    return CliAgentManager(paths.global_config_file)


@click.group()
def agent() -> None:
    """Manage agent profiles."""


@agent.command("list")
def agent_list() -> None:
    """List all agent profiles."""
    mgr = _get_manager()
    agents = mgr.list()
    default_name = mgr.default_agent_name

    table = Table(title="Agent Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Workspace")
    table.add_column("Default", justify="center")

    for a in agents:
        is_default = "●" if a.name == default_name else ""
        table.add_row(
            a.name,
            a.provider or "(inherit)",
            a.model or "(inherit)",
            a.workspace_dir or "(inherit)",
            is_default,
        )

    console.print(table)


@agent.command("create")
@click.argument("name")
@click.option("--provider", "-p", default=None, help="Provider name (from config)")
@click.option("--model", "-m", default=None, help="Model ID")
@click.option("--backend", default=None, help="Backend type or JSON spec")
@click.option("--workspace-dir", default=None, help="Workspace directory (absolute)")
def agent_create(
    name: str,
    provider: str | None,
    model: str | None,
    backend: str | None,
    workspace_dir: str | None,
) -> None:
    """Create a new agent profile."""
    mgr = _get_manager()

    parsed_backend: str | dict[str, object] | None = None
    if backend:
        try:
            parsed_backend = json.loads(backend)
        except json.JSONDecodeError:
            parsed_backend = backend

    profile = AgentProfile(
        name=name,
        provider=provider,
        model=model,
        backend=parsed_backend,
        workspace_dir=workspace_dir,
    )

    try:
        mgr.create(profile)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise SystemExit(1) from exc

    console.print(f"[green]✓[/] Agent '{name}' created.")


@agent.command("remove")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def agent_remove(name: str, yes: bool) -> None:
    """Remove an agent profile."""
    mgr = _get_manager()
    if not yes and not click.confirm(f"Remove agent '{name}'?"):
        return

    try:
        mgr.remove(name)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise SystemExit(1) from exc

    console.print(f"[green]✓[/] Agent '{name}' removed.")


@agent.command("show")
@click.argument("name")
def agent_show(name: str) -> None:
    """Show resolved configuration for an agent."""
    mgr = _get_manager()
    try:
        resolved = mgr.resolve(name)
    except (KeyError, ValueError) as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise SystemExit(1) from exc

    for pcfg in resolved.get("providers", {}).values():
        if isinstance(pcfg, dict) and pcfg.get("api_key"):
            key = pcfg["api_key"]
            pcfg["api_key"] = key[:4] + "***" + key[-4:] if len(key) > 8 else "***"

    console.print(json.dumps(resolved, indent=2, ensure_ascii=False))


@agent.command("set-default")
@click.argument("name")
def agent_set_default(name: str) -> None:
    """Set the default agent profile."""
    mgr = _get_manager()
    try:
        mgr.set_default(name)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise SystemExit(1) from exc

    console.print(f"[green]✓[/] Default agent set to '{name}'.")
