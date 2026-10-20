"""The `octop-harness config` command group — configuration management."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from octop_harness.cli.config.loader import load_config
from octop_harness.cli.config.paths import CliPaths

console = Console()


@click.group()
def config() -> None:
    """Manage CLI and agent configuration."""


@config.command("list")
def config_list() -> None:
    """List all configuration values."""
    _, cli_cfg = load_config(project_dir=Path.cwd())

    table = Table(title="CLI Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    for key, value in cli_cfg.to_dict().items():
        table.add_row(key, str(value))
    console.print(table)

    agent_cfg, _ = load_config(project_dir=Path.cwd())
    if agent_cfg and "providers" in agent_cfg:
        ptable = Table(title="Providers")
        ptable.add_column("Name", style="cyan")
        ptable.add_column("Base URL")
        ptable.add_column("Models")
        for name, pcfg in agent_cfg["providers"].items():
            models = ", ".join(m["id"] for m in pcfg.get("models", []))
            ptable.add_row(name, pcfg.get("base_url", ""), models)
        console.print(ptable)


@config.command("get")
@click.argument("key")
def config_get(key: str) -> None:
    """Get a configuration value by key."""
    _, cli_cfg = load_config(project_dir=Path.cwd())
    data = cli_cfg.to_dict()
    if key in data:
        console.print(f"{key} = {data[key]}")
    else:
        console.print(f"[red]Unknown key:[/] {key}")
        raise SystemExit(1)


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value."""
    paths = CliPaths(project_dir=Path.cwd())
    config_file = paths.project_config_file

    data: dict[str, object] = {}
    if config_file.is_file():
        data = json.loads(config_file.read_text(encoding="utf-8"))

    cli_section = data.setdefault("cli", {})
    if not isinstance(cli_section, dict):
        cli_section = {}
        data["cli"] = cli_section

    # Type coercion for booleans and integers
    parsed_value: object
    if value.lower() in ("true", "false"):
        parsed_value = value.lower() == "true"
    elif value.isdigit():
        parsed_value = int(value)
    else:
        parsed_value = value

    cli_section[key] = parsed_value

    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]Set[/] {key} = {parsed_value}")


@config.group("provider")
def provider() -> None:
    """Manage model providers."""


@provider.command("list")
def provider_list() -> None:
    """List configured providers."""
    agent_cfg, _ = load_config(project_dir=Path.cwd())
    if not agent_cfg or "providers" not in agent_cfg:
        console.print("[dim]No providers configured. Run: octop-harness config provider add[/]")
        return

    table = Table(title="Providers")
    table.add_column("Name", style="cyan")
    table.add_column("Protocol")
    table.add_column("Base URL")
    table.add_column("Models")
    for name, pcfg in agent_cfg["providers"].items():
        models = ", ".join(m["id"] for m in pcfg.get("models", []))
        table.add_row(name, pcfg.get("protocol", "openai"), pcfg.get("base_url", ""), models)
    console.print(table)


@provider.command("add")
@click.option("--name", prompt="Provider name", help="Provider identifier")
@click.option("--base-url", prompt="Base URL", help="API base URL")
@click.option("--api-key", prompt="API Key", hide_input=True, help="API key")
@click.option("--protocol", type=click.Choice(["openai", "anthropic", "bedrock"]), default="openai")
@click.option("--model-id", prompt="Model ID", help="Model identifier")
def provider_add(name: str, base_url: str, api_key: str, protocol: str, model_id: str) -> None:
    """Interactively add a new provider."""
    paths = CliPaths(project_dir=Path.cwd())
    config_file = paths.project_config_file

    data: dict[str, object] = {}
    if config_file.is_file():
        data = json.loads(config_file.read_text(encoding="utf-8"))

    providers = data.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        data["providers"] = providers

    providers[name] = {
        "base_url": base_url,
        "api_key": api_key,
        "protocol": protocol,
        "models": [{"id": model_id}],
    }

    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]Added provider:[/] {name} ({base_url})")


@provider.command("remove")
@click.argument("name")
def provider_remove(name: str) -> None:
    """Remove a provider by name."""
    paths = CliPaths(project_dir=Path.cwd())
    config_file = paths.project_config_file

    if not config_file.is_file():
        console.print("[red]No config file found.[/]")
        raise SystemExit(1)

    data = json.loads(config_file.read_text(encoding="utf-8"))
    providers = data.get("providers", {})
    if name not in providers:
        console.print(f"[red]Provider not found:[/] {name}")
        raise SystemExit(1)

    del providers[name]
    config_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]Removed provider:[/] {name}")
