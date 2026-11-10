"""octop migrate — bring an OpenClaw or Hermes Agent setup into an Octop expert."""

from __future__ import annotations

import json as _json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from octop.cli.support.ctx import json_output_enabled, require_agent

_SECTIONS = ("models", "files", "skills", "mcp", "channels")
_STATUS_STYLE = {"migrated": "green", "skipped": "yellow", "failed": "red"}


@click.group("migrate")
def migrate() -> None:
    """Migrate models, persona and memory files, skills, MCP servers and channels."""


def _source_options(fn: Callable[..., Any]) -> Callable[..., Any]:
    options = [
        click.option(
            "--from",
            "source_dir",
            default=None,
            type=click.Path(file_okay=False),
            help="Source home directory (default: auto-detect).",
        ),
        click.option("--agent", "agent_id", default=None, help="Expert to migrate into."),
        click.option("--user", "as_user", default=None, help="Owner of the migrated connectors."),
        click.option(
            "--skip",
            multiple=True,
            type=click.Choice(_SECTIONS),
            help="Leave one kind of content out (repeatable).",
        ),
        click.option(
            "--overwrite",
            is_flag=True,
            help="Replace existing workspace files and skills, and the default model.",
        ),
        click.option("--dry-run", is_flag=True, help="Show what would happen; write nothing."),
    ]
    for option in reversed(options):
        fn = option(fn)
    return fn


@migrate.command("openclaw")
@_source_options
def openclaw(**kwargs: Any) -> None:
    """Migrate from OpenClaw (~/.openclaw)."""
    from octop.infra.migration.openclaw import find_openclaw_home, read_openclaw

    _run("OpenClaw", find_openclaw_home, read_openclaw, **kwargs)


@migrate.command("hermes")
@_source_options
def hermes(**kwargs: Any) -> None:
    """Migrate from Hermes Agent (~/.hermes)."""
    from octop.infra.migration.hermes import find_hermes_home, read_hermes

    _run("Hermes", find_hermes_home, read_hermes, **kwargs)


def _run(
    label: str,
    find_home: Callable[[], Path | None],
    read: Callable[[Path], Any],
    *,
    source_dir: str | None,
    agent_id: str | None,
    as_user: str | None,
    skip: tuple[str, ...],
    overwrite: bool,
    dry_run: bool,
) -> None:
    from octop.cli.support.acting import resolve_cli_acting_user_id
    from octop.cli.support.db import resolve_cli_locale
    from octop.cli.support.embedded_ops import apply_migration
    from octop.i18n import tr
    from octop.infra.errors import OctopError

    locale = resolve_cli_locale()
    home = Path(source_dir).expanduser() if source_dir else find_home()
    if home is None or not home.is_dir():
        raise click.ClickException(tr("migrate.not_found", locale, source=label))
    aid = require_agent(agent_id)
    try:
        user_id = resolve_cli_acting_user_id(aid, as_user)
        report = apply_migration(
            read(home),
            agent_id=aid,
            user_id=user_id,
            sections=tuple(s for s in _SECTIONS if s not in skip),
            overwrite=overwrite,
            dry_run=dry_run,
        )
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output_enabled():
        click.echo(_json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_report(report, label=label, agent_id=aid, locale=locale)
    if report.count("failed"):
        raise SystemExit(1)


def _tilde(path: str) -> str:
    """Show paths under the user's home the way they are usually written."""
    try:
        return f"~/{Path(path).relative_to(Path.home()).as_posix()}"
    except ValueError:
        return path


def _print_report(report: Any, *, label: str, agent_id: str, locale: str) -> None:
    from rich.console import Console
    from rich.table import Table

    from octop.i18n import tr

    console = Console(file=sys.stdout, highlight=False)
    if not report.items and not report.notes:
        console.print(tr("migrate.nothing", locale, home=_tilde(report.home)))
        return

    title = tr("migrate.title", locale, source=label, home=_tilde(report.home), agent=agent_id)
    table = Table(title=title, title_justify="left")
    for column in ("section", "item", "status", "note"):
        table.add_column(tr(f"migrate.column.{column}", locale))
    for item in report.items:
        status = "would_migrate" if report.dry_run and item.status == "migrated" else item.status
        note = (
            tr(f"migrate.reason.{item.reason}", locale, detail=item.detail) if item.reason else ""
        )
        table.add_row(
            tr(f"migrate.section.{item.section}", locale),
            item.name,
            f"[{_STATUS_STYLE[item.status]}]{tr(f'migrate.status.{status}', locale)}[/]",
            note,
        )
    if report.items:
        console.print(table)
    for note in report.notes:
        console.print(f"[dim]•[/] {tr(f'migrate.note.{note.code}', locale, **note.params)}")

    console.print(
        tr(
            "migrate.summary_dry_run" if report.dry_run else "migrate.summary",
            locale,
            migrated=report.count("migrated"),
            skipped=report.count("skipped"),
            failed=report.count("failed"),
        )
    )
    if report.dry_run:
        console.print(tr("migrate.dry_run_hint", locale))
    elif report.count("migrated"):
        console.print(tr("migrate.restart_hint", locale))
