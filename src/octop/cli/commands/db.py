"""Offline SQLite health inspection and recovery commands (``octop db``)."""

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


@click.group()
def db() -> None:
    """Inspect and recover local SQLite databases under OCTOP_HOME."""


def _format_mb(nbytes: int) -> str:
    return f"{nbytes / (1024 * 1024):.2f} MB"


def _print_report(report: SqliteCheckReport) -> None:
    status = "OK" if report.ok else "CORRUPT"
    extra = f" (wal {_format_mb(report.wal_bytes)})" if report.wal_bytes else ""
    click.echo(f"[{status}] {report.path} — {_format_mb(report.size_bytes)}{extra}")
    if not report.ok and report.error:
        click.echo(f"        {report.error}")


@db.command(name="doctor")
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
def doctor(full: bool, target_path: Path | None) -> None:
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
                "Stop Octop first, then run `octop db recover --all-corrupt` "
                "(or `octop db recover <path>`)."
            )
        else:
            click.echo(f"\nAll {len(reports)} SQLite database(s) passed integrity check.")

    if corrupt:
        raise click.exceptions.Exit(1)


@db.command(name="recover")
@click.argument("target", type=click.Path(path_type=Path), required=False, default=None)
@click.option(
    "--all-corrupt",
    is_flag=True,
    default=False,
    help="Recover every SQLite file under OCTOP_HOME that fails PRAGMA quick_check.",
)
@click.option(
    "--reset",
    is_flag=True,
    default=False,
    help="Archive the damaged database and remove it so Octop recreates a clean file.",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    default=False,
    help="Skip the interactive confirmation prompt.",
)
def recover(target: Path | None, all_corrupt: bool, reset: bool, yes: bool) -> None:
    """Back up and recover a corrupted SQLite file (stop Octop before running)."""
    if target is None and not all_corrupt:
        raise click.UsageError("Specify a database TARGET path or pass --all-corrupt.")
    if target is not None and all_corrupt:
        raise click.UsageError("Pass either TARGET or --all-corrupt, not both.")

    if all_corrupt:
        reports = [
            inspect_sqlite_file(p) for p in discover_sqlite_files(PathLayout.from_env().root)
        ]
        targets = [Path(r.path) for r in reports if not r.ok]
    else:
        assert target is not None
        if not target.is_file():
            raise click.ClickException(f"SQLite file not found: {target}")
        targets = [target]

    if not targets:
        if json_output_enabled():
            click.echo(json.dumps({"recovered": []}, ensure_ascii=False))
        else:
            click.echo("No corrupted SQLite databases found.")
        return

    mode: Literal["recover", "reset"] = "reset" if reset else "recover"
    if not yes:
        action = "archive and reset" if reset else "back up and recover"
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
