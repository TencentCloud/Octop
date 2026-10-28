"""Validate the persisted ``~/.octop/env`` file."""

from __future__ import annotations

import click

from octop.infra.utils.env_file import env_file_path, validate_env_text
from octop.infra.utils.paths import PathLayout


@click.group("env")
def env() -> None:
    """Inspect the persisted environment file."""


@env.command("validate")
def validate() -> None:
    """Report malformed entries without changing the file."""
    path = env_file_path(PathLayout.from_env().root)
    if not path.is_file():
        click.echo(f"OK: {path} does not exist")
        return
    issues = validate_env_text(path.read_text(encoding="utf-8"))
    if not issues:
        click.echo(f"OK: {path}")
        return
    for issue in issues:
        click.echo(f"! {path}:{issue.line} [{issue.code}] {issue.message}")
    raise click.exceptions.Exit(1)
