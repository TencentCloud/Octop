"""`octop captcha` — offline captcha maintenance (lockout escape hatch)."""

from __future__ import annotations

import click

from octop.cli.support.db import open_cli_services
from octop.infra.auth.captcha.store import SETTINGS_KEY


@click.group("captcha")
def captcha() -> None:
    """Login captcha maintenance against the local database."""


@captcha.command("reset")
def reset() -> None:
    """Clear stored captcha settings so login falls back to the slider default.

    Use this when a misconfigured provider (wrong keys, unreachable vendor,
    hostname not allowlisted) locks everyone out of the dashboard: the
    settings UI requires login, so the only offline escape is this command
    or restoring a backup. Boot-env captcha (OCTOP_CAPTCHA_*) is not touched
    — unset those in the environment file if they are the lockout cause.
    If `octop run` is already running, restart it for the change to apply.
    """
    with open_cli_services() as services:
        if services.settings_repo.get(SETTINGS_KEY) is None:
            click.echo("captcha settings already at default (nothing stored)")
            return
        services.settings_repo.delete(SETTINGS_KEY)
    click.echo(
        "captcha settings cleared; login now uses the built-in slider "
        "(restart `octop run` if it is running)"
    )
