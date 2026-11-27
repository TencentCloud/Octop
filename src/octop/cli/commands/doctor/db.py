"""SQLite health check for ``octop doctor db``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import click

from octop.cli.support.ctx import json_output_enabled
from octop.infra.db.sqlite_doctor import (
    SqliteCheckReport,
    discover_sqlite_files,
    inspect_sqlite_file,
    recover_sqlite_file,
)
from octop.infra.utils.paths import PathLayout


def _format_mb(nbytes: int) -> str:
    return f"{nbytes / (1024 * 1024):.2f} MB"


def _print_report(report: SqliteCheckReport) -> None:
    status = "OK" if report.ok else "CORRUPT"
    extra = f" (wal {_format_mb(report.wal_bytes)})" if report.wal_bytes else ""
    click.echo(f"[{status}] {report.path} — {_format_mb(report.size_bytes)}{extra}")
    if not report.ok and report.error:
        click.echo(f"        {report.error}")


@click.command(name="db")
@click.option(
    "--full",
    is_flag=True,
    default=False,
    help="Run PRAGMA integrity_check instead of the faster PRAGMA quick_check.",
)
@click.option(
    "--path",
    "target_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Check a single SQLite file instead of scanning OCTOP_HOME.",
)
@click.option(
    "--fix",
    is_flag=True,
    default=False,
    help="Repair corrupted SQLite files after checking them.",
)
@click.option(
    "--reset",
    is_flag=True,
    default=False,
    help="Archive damaged databases and remove them so Octop recreates clean files.",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    default=False,
    help="Skip the interactive confirmation prompt when fixing databases.",
)
def database(full: bool, target_path: Path | None, fix: bool, reset: bool, yes: bool) -> None:
    """Inspect local SQLite databases under OCTOP_HOME."""
    if not fix:
        if reset or yes:
            raise click.UsageError("--reset and --yes require --fix.")
        _check_databases(full, target_path)
        return
    _fix_databases(target_path, reset, yes)


def _check_databases(full: bool, target_path: Path | None) -> None:
    """Check SQLite databases under OCTOP_HOME for corruption."""
    paths = (
        [target_path]
        if target_path is not None
        else discover_sqlite_files(PathLayout.from_env().root)
    )
    reports = [inspect_sqlite_file(p, full=full) for p in paths]
    corrupt = [r for r in reports if not r.ok]

    if json_output_enabled():
        click.echo(
            json.dumps(
                {
                    "ok": not corrupt,
                    "checked": len(reports),
                    "corrupt": len(corrupt),
                    "databases": [r.to_dict() for r in reports],
                },
                ensure_ascii=False,
            )
        )
    else:
        if not reports:
            click.echo(f"No SQLite databases found under {PathLayout.from_env().root}.")
            return
        for report in reports:
            _print_report(report)
        if corrupt:
            click.echo(
                f"\nFound {len(corrupt)} corrupted database(s). "
                "Stop Octop first, then run `octop doctor db --fix` "
                "(or `octop doctor db --fix --path <path>`)."
            )
        else:
            click.echo(f"\nAll {len(reports)} SQLite database(s) passed integrity check.")

    if corrupt:
        raise click.exceptions.Exit(1)


def _fix_databases(target_path: Path | None, reset: bool, yes: bool) -> None:
    """Back up and repair corrupted SQLite files under OCTOP_HOME."""
    if target_path is None:
        reports = [
            inspect_sqlite_file(p) for p in discover_sqlite_files(PathLayout.from_env().root)
        ]
        targets = [Path(r.path) for r in reports if not r.ok]
    else:
        if not target_path.is_file():
            raise click.ClickException(f"SQLite file not found: {target_path}")
        targets = [target_path]

    if not targets:
        if json_output_enabled():
            click.echo(json.dumps({"recovered": []}, ensure_ascii=False))
        else:
            click.echo("No corrupted SQLite databases found.")
        return

    mode: Literal["recover", "reset"] = "reset" if reset else "recover"
    if not yes:
        action = "archive and reset" if reset else "back up and fix"
        prompt = (
            f"Make sure the Octop server is stopped before modifying SQLite files.\n"
            f"Proceed to {action} {len(targets)} database file(s)?"
        )
        if not click.confirm(prompt, default=False):
            raise click.Abort()

    results = []
    for item in targets:
        try:
            result = recover_sqlite_file(item, mode=mode)
        except (OSError, ValueError, RuntimeError) as exc:
            raise click.ClickException(str(exc)) from exc
        results.append(result)

    if json_output_enabled():
        click.echo(json.dumps({"recovered": [r.to_dict() for r in results]}, ensure_ascii=False))
    else:
        for res in results:
            click.echo(f"[OK] {res.path} ({res.method}) — backup saved to {res.backup_path}")
