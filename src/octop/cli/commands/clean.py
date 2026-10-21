"""`octop clean` — remove CLI state and (optionally) all agentbuddy data."""

from __future__ import annotations

import shutil
from pathlib import Path

import click

from octop.infra.utils.paths import PathLayout


def _cli_targets() -> list[Path]:
    paths = PathLayout.from_env()
    return [paths.root / "cli_state.json"]


def _all_targets() -> list[Path]:
    return [PathLayout.from_env().root]


@click.command("clean")
@click.option("--all", "wipe_all", is_flag=True, default=False, help="Wipe ALL of ~/.agentbuddy.")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation.")
@click.option("--dry-run", is_flag=True, default=False, help="Show targets without deleting.")
def clean(wipe_all: bool, yes: bool, dry_run: bool) -> None:
    """Remove the CLI state file (default) or wipe everything (--all)."""
    targets = _all_targets() if wipe_all else _cli_targets()
    for t in targets:
        click.echo(("would remove " if dry_run else "removing ") + str(t))
    if dry_run:
        return
    if wipe_all and not yes:
        click.confirm("This deletes ALL agentbuddy data (DB, configs, logs). Continue?", abort=True)
    elif not yes:
        click.confirm("Remove CLI state?", abort=True)
    for t in targets:
        if not t.exists():
            continue
        if t.is_dir():
            shutil.rmtree(t)
        else:
            t.unlink()
    click.echo("done")
