"""`octop update` — self-upgrade via pip or uv."""

from __future__ import annotations

import click

from octop.cli.support.db import resolve_cli_locale
from octop.infra.setup.self_update import (
    fetch_pypi_info,
    get_editable_path,
    get_local_version,
    is_newer,
    is_prerelease,
    resolve_venv_python,
    run_upgrade,
)


@click.command("update")
@click.option("--check", is_flag=True, default=False, help="Only check, do not install.")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose installer output.")
@click.option(
    "--allow-prerelease",
    "allow_prerelease",
    is_flag=True,
    default=False,
    help="Include and allow installing pre-releases (alpha / beta / rc / dev).",
)
def update(check: bool, yes: bool, verbose: bool, allow_prerelease: bool) -> None:
    """Check for and install a newer Octop release."""
    current = get_local_version()
    info = fetch_pypi_info()
    click.echo(f"installed: {current}")
    if info is None:
        click.echo(
            "could not reach PyPI — check your network or proxy settings and retry",
            err=True,
        )
        raise SystemExit(1)
    latest = info.version if allow_prerelease else info.latest_stable
    if latest is None:
        click.echo("no stable release available (pass --allow-prerelease to include pre-releases)")
        return
    click.echo(f"latest:    {latest}")
    if not is_newer(latest, current):
        click.echo("already up to date")
        return
    if check:
        return

    editable_path = get_editable_path()
    if editable_path:
        click.echo(
            f"This installation is running from source ({editable_path}).",
            err=True,
        )
        click.echo(f"To upgrade: cd {editable_path} && git pull")
        raise SystemExit(1)

    if not yes:
        click.confirm(f"Upgrade octop from {current} to {latest}?", abort=True)

    venv_python = resolve_venv_python()
    click.echo(f"target python: {venv_python}")
    result = run_upgrade(
        verbose=verbose,
        allow_prerelease=is_prerelease(latest),
        version=latest,
        locale=resolve_cli_locale(),
    )
    if not result.success:
        click.echo(f"upgrade failed: {result.error}", err=True)
        for err in result.mirror_errors:
            click.echo(f"  {err}", err=True)
        raise SystemExit(1)

    click.echo(result.message or "upgrade complete")
    if result.installed_version:
        click.echo(f"installed: {result.installed_version}")
