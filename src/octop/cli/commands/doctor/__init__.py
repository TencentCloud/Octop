"""Offline health checks (``octop doctor``).

Each check is a module in this package and is registered on ``doctor``.
"""

from __future__ import annotations

import click

from octop.cli.commands.doctor.db import database


@click.group()
def doctor() -> None:
    """Run offline health checks."""


doctor.add_command(database)
