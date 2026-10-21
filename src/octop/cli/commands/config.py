"""octop config — CLI defaults (user / agent pins)."""

from __future__ import annotations

import json

import click

from octop.cli.support.state import default_state_path, load, save


@click.group("config")
def config_group() -> None:
    """View or update CLI defaults (~/.agentbuddy/cli_state.json)."""


@config_group.command("show")
def show_config() -> None:
    """Print pinned default user and agent."""
    state = load(default_state_path())
    click.echo(
        json.dumps(
            {
                "default_user": state.default_user,
                "default_agent": state.default_agent,
            },
            indent=2,
        )
    )


@config_group.command("set-user")
@click.argument("username")
def set_user(username: str) -> None:
    """Pin default --user for subcommands."""
    path = default_state_path()
    state = load(path)
    state.default_user = username
    save(path, state)
    click.echo(f"default_user set to {username}")
