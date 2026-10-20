"""Click CLI entry point: the `harness` command group."""

from __future__ import annotations

from pathlib import Path

from octop_harness.cli import _check_cli_deps

try:
    _check_cli_deps()
except ImportError as exc:
    raise SystemExit(str(exc)) from None

import click

from octop_harness.cli import __version__, load_dotenv_files


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="octop-harness-cli")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Harness Agent CLI — chat with AI agents from your terminal."""
    load_dotenv_files(Path.cwd())
    if ctx.invoked_subcommand is None:
        from octop_harness.cli.commands.chat import chat

        ctx.invoke(chat)


def _register_commands() -> None:
    """Register all subcommands."""
    from octop_harness.cli.commands.agent_cmd import agent
    from octop_harness.cli.commands.chat import chat
    from octop_harness.cli.commands.config_cmd import config
    from octop_harness.cli.commands.init_cmd import init
    from octop_harness.cli.commands.skill import skill
    from octop_harness.cli.commands.update import update

    cli.add_command(agent)
    cli.add_command(chat)
    cli.add_command(config)
    cli.add_command(skill)
    cli.add_command(init)
    cli.add_command(update)


_register_commands()
