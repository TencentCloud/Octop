"""Configuration management for the CLI.

The pure IO portion (``DEFAULTS``, ``load_config``, ``save_config``,
``get_config_path``, ``set_config_path``) lives in
:mod:`octop_memory._config_io` so non-CLI hosts (e.g. ``MemoryService``)
can read the same config file without pulling in ``click``.
This module layers click commands and ``get_memory`` (which builds a
:class:`Memory` from the resolved CLI context) on top of those primitives.
"""

from __future__ import annotations

import json

import click

from octop_memory._config_io import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULTS,
    get_config_path,
    load_config,
    save_config,
    set_config_path,
)
from octop_memory.core import Memory

__all__ = [
    "CONFIG_DIR",
    "CONFIG_FILE",
    "DEFAULTS",
    "config_group",
    "get_config_path",
    "get_memory",
    "load_config",
    "save_config",
    "set_config_path",
]


def get_memory(ctx: click.Context) -> Memory:
    """Build a Memory instance from resolved configuration.

    Resolution order (highest priority first):
    1. CLI flags (--backend, --db, --dsn)
    2. Environment variables (OCTOP_MEMORY_BACKEND, OCTOP_MEMORY_DB, OCTOP_MEMORY_DSN)
    3. Config file (~/.octop-memory/config.json)
    4. Defaults
    """
    # ctx.obj already has the resolved values from CLI flags + env vars
    backend = ctx.obj["backend"]
    namespace = ctx.obj["namespace"]
    db = ctx.obj["db"]
    dsn = ctx.obj["dsn"]

    # Build backend_config based on backend type
    if backend == "sqlite":
        backend_config = {"db_path": db}
    elif backend == "postgres":
        backend_config = {"dsn": dsn}
    elif backend == "qdrant":
        # Load qdrant config from config file
        file_config = load_config()
        backend_config = file_config.get("qdrant", {})
    else:
        backend_config = {}

    return Memory(namespace=namespace, backend=backend, backend_config=backend_config)


# --- CLI Commands ---


@click.group(name="config")
@click.pass_context
def config_group(ctx: click.Context) -> None:
    """Manage CLI configuration."""
    pass


@config_group.command()
@click.pass_context
def show(ctx: click.Context) -> None:
    """Display the resolved configuration."""
    output_json = ctx.obj["output_json"]
    config_file = get_config_path()
    file_config = load_config()

    # Show effective config (with overrides)
    effective = {
        "backend": ctx.obj["backend"],
        "namespace": ctx.obj["namespace"],
        "config_file": str(config_file),
        "file_config": file_config,
    }

    if ctx.obj["backend"] == "sqlite":
        effective["sqlite"] = {"db_path": ctx.obj["db"]}
    elif ctx.obj["backend"] == "postgres":
        effective["postgres"] = {"dsn": ctx.obj["dsn"]}

    if output_json:
        click.echo(json.dumps({"status": "ok", "data": effective}, indent=2))
    else:
        click.echo(f"Config file: {config_file}")
        click.echo(f"Backend:     {effective['backend']}")
        click.echo(f"Namespace:   {effective['namespace']}")
        if effective["backend"] == "sqlite":
            click.echo(f"DB path:     {effective['sqlite']['db_path']}")
        elif effective["backend"] == "postgres":
            click.echo(f"DSN:         {effective['postgres']['dsn']}")
        click.echo(f"\nFile contents ({config_file}):")
        if config_file.exists():
            click.echo(json.dumps(file_config, indent=2))
        else:
            click.echo("  (no config file found)")


@config_group.command(name="set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def set_cmd(ctx: click.Context, key: str, value: str) -> None:
    """Set a configuration value.

    Supports dotted keys: e.g., 'sqlite.db_path', 'postgres.dsn', 'backend', 'namespace'
    """
    output_json = ctx.obj["output_json"]
    file_config = load_config()

    # Handle dotted keys
    parts = key.split(".", 1)
    if len(parts) == 2:
        section, subkey = parts
        if section not in file_config:
            file_config[section] = {}
        if not isinstance(file_config[section], dict):
            file_config[section] = {}
        file_config[section][subkey] = value
    else:
        file_config[key] = value

    save_config(file_config)

    if output_json:
        click.echo(json.dumps({"status": "ok", "data": {"key": key, "value": value}}))
    else:
        click.echo(f"Set {key} = {value}")


@config_group.command()
@click.pass_context
def path(ctx: click.Context) -> None:
    """Print the config file path."""
    click.echo(str(get_config_path()))
