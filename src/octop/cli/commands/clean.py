"""`octop clean` — remove CLI state and (optionally) Octop application data."""

from __future__ import annotations

from pathlib import Path

import click

from octop.infra.utils.install_reset import (
    InstallResetError,
    partition_install_root,
    remove_install_entry,
)
from octop.infra.utils.paths import PathLayout


def _cli_targets() -> list[Path]:
    paths = PathLayout.from_env()
    return [paths.root / "cli_state.json"]


def _all_targets() -> list[Path]:
    """Application state under the install root. Runtime dirs stay put."""
    try:
        state, _runtime = partition_install_root(PathLayout.from_env().root)
    except InstallResetError as exc:
        raise click.ClickException(str(exc)) from None
    return state


@click.command("clean")
@click.option(
    "--all",
    "wipe_all",
    is_flag=True,
    default=False,
    help="Delete Octop data under ~/.octop. Keeps the install runtime (venv/, bin/).",
)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation.")
@click.option("--dry-run", is_flag=True, default=False, help="Show targets without deleting.")
def clean(wipe_all: bool, yes: bool, dry_run: bool) -> None:
    """Remove the CLI state file (default) or Octop data (--all)."""
    targets = _all_targets() if wipe_all else _cli_targets()
    for t in targets:
        click.echo(("would remove " if dry_run else "removing ") + str(t))
    if dry_run:
        return
    if wipe_all and not yes:
        click.confirm(
            "This deletes Octop data (DB, configs, agents, logs). "
            "The install runtime (venv, bin) is kept. Continue?",
            abort=True,
        )
    elif not yes:
        click.confirm("Remove CLI state?", abort=True)
    for t in targets:
        if not t.exists():
            continue
        remove_install_entry(t)
    click.echo("done")
