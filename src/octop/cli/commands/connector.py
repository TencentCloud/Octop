"""Offline connector installation for external MCP installers."""

from __future__ import annotations

import json
from typing import Any, NoReturn, TextIO

import click

from octop.cli.support.acting import resolve_cli_acting_user_id
from octop.cli.support.ctx import json_output_enabled
from octop.cli.support.db import open_cli_services
from octop.i18n import tr
from octop.infra.connectors.installation import ConnectorInstaller
from octop.infra.errors import ErrorCode, OctopError


@click.group(help=tr("connector.install.help", "en"))
def connector() -> None:
    """Install, inspect or remove built-in connector instances."""


def _execute(action: str, kind: str, name: str, user: str | None, config: Any = None) -> None:
    locale = "en"
    try:
        uid = resolve_cli_acting_user_id(as_user=user)
        with open_cli_services() as services:
            row = services.user_repo.get(uid)
            locale = row.locale if row and row.locale in ("zh", "en") else "en"
            installer = ConnectorInstaller(services, user_id=uid, locale=locale)
            if action == "install":
                if not isinstance(config, dict):
                    raise OctopError(
                        ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
                        tr("connector.install.invalid_config", locale),
                    )
                result = installer.install(kind, name.strip(), config)
            elif action == "get":
                result = installer.get(kind, name.strip())
            else:
                result = installer.remove(kind, name.strip())
        result["message"] = tr(f"connector.install.{action}", locale)
        click.echo(
            json.dumps(result, ensure_ascii=False) if json_output_enabled() else result["message"]
        )
    except OctopError as exc:
        _fail(exc, locale)


def _fail(exc: OctopError, locale: str) -> NoReturn:
    message = tr("connector.install.failed", locale, reason=exc.message)
    if exc.code == ErrorCode.NOT_FOUND:
        message += " " + tr("connector.install.user_hint", locale)
    if json_output_enabled():
        click.echo(json.dumps({"ok": False, "code": exc.code.value, "message": message}))
    else:
        click.echo(message, err=True)
    raise SystemExit(1) from exc


@connector.command("install", help=tr("connector.install.install_help", "en"))
@click.argument("kind", type=click.Choice(["open-design"]))
@click.option(
    "--name", default="open-design", show_default=True, help=tr("connector.install.name_help", "en")
)
@click.option("--user", default=None, help=tr("connector.install.user_help", "en"))
@click.option(
    "--config-file",
    type=click.File("r", encoding="utf-8"),
    required=True,
    help=tr("connector.install.config_help", "en"),
)
def install(kind: str, name: str, user: str | None, config_file: TextIO) -> None:
    """Install a launch spec; --config-file - reads JSON from stdin."""
    try:
        config = json.load(config_file)
    except ValueError:
        _fail(
            OctopError(
                ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
                tr("connector.install.invalid_config", "en"),
            ),
            "en",
        )
    _execute("install", kind, name, user, config)


@connector.command("get", help=tr("connector.install.get_help", "en"))
@click.argument("kind", type=click.Choice(["open-design"]))
@click.option(
    "--name", default="open-design", show_default=True, help=tr("connector.install.name_help", "en")
)
@click.option("--user", default=None, help=tr("connector.install.user_help", "en"))
def get(kind: str, name: str, user: str | None) -> None:
    """Inspect registration without printing credentials."""
    _execute("get", kind, name, user)


@connector.command("remove", help=tr("connector.install.remove_help", "en"))
@click.argument("kind", type=click.Choice(["open-design"]))
@click.option(
    "--name", default="open-design", show_default=True, help=tr("connector.install.name_help", "en")
)
@click.option("--user", default=None, help=tr("connector.install.user_help", "en"))
def remove(kind: str, name: str, user: str | None) -> None:
    """Remove this user's named instance; repeated removal succeeds."""
    _execute("remove", kind, name, user)
