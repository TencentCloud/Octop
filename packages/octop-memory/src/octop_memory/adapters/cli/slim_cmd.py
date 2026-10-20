"""Simple, lossless SQLite checkpoint maintenance with automatic backups."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

import click

from octop_memory.application.checkpoint_maintenance import maintain_checkpoints


@click.command(name="slim")
@click.argument("database", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--apply", is_flag=True, help="Back up, deduplicate checkpoint fields, and reclaim file space.")
@click.option("--offline", is_flag=True, help="Confirm all processes using this database have been stopped.")
@click.pass_context
def slim_cmd(ctx: click.Context, database: Path, apply: bool, offline: bool) -> None:
    """Preview or slim DATABASE without deleting checkpoint history (SQLite only).

    Default: read-only preview. To apply, stop all database users first, then
    pass --apply --offline. A uniquely named backup is created beside DATABASE;
    deduplication and VACUUM run automatically. --offline does not stop services.

    Keep free disk space for a full backup and VACUUM temporary files. Existing
    checkpoint IDs, messages and memory records are preserved. Readers must
    support the shared-content checkpoint format after migration.
    """
    if apply and not offline:
        raise click.UsageError("Stop all processes using DATABASE, then pass --apply --offline.")
    if offline and not apply:
        raise click.UsageError("--offline is only used with --apply; omit both for a read-only preview.")
    if ctx.obj["backend"] != "sqlite":
        raise click.ClickException("db slim is SQLite-only; PostgreSQL keeps its existing saver")

    database = database.resolve()
    backup = None
    if apply:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup = database.with_name(f"{database.name}.before-slim.{stamp}.{uuid.uuid4().hex[:8]}.bak")
        # Keep the location visible even if a later batch or VACUUM fails.
        click.echo(f"Backup destination: {backup}", err=True)
    try:
        report = maintain_checkpoints(database, apply=apply, offline=offline, backup=backup, vacuum=apply)
    except (ValueError, OSError, sqlite3.Error, ImportError) as exc:
        detail = str(exc)
        if detail == "SQLite quick_check failed":
            detail += (
                f" (SQLite {sqlite3.sqlite_version}). Read-only FTS checks fail in some older SQLite runtimes; "
                "verify with a compatible runtime or a database copy before applying."
            )
        raise click.ClickException(detail) from exc

    report["database"] = str(database)
    report["backup_path"] = str(backup) if backup else None
    if ctx.obj.get("output_json"):
        click.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return

    stats = report["stats"]
    mib = 1024 * 1024
    before = report["before"]
    after = report["after"]
    click.echo(f"Database: {database}")
    click.echo(f"Checkpoints scanned: {stats['scanned']}")
    if not apply:
        click.echo(f"Checkpoints eligible for deduplication: {stats['rewritten']}")
        click.echo(f"Current file: {before['file_bytes'] / mib:.2f} MiB; WAL: {before['wal_bytes'] / mib:.2f} MiB")
        click.echo(
            f"Checkpoint payload: {stats['payload_before'] / mib:.2f} -> {stats['payload_after'] / mib:.2f} MiB "
            "(excludes shared blobs/indexes; not a file-size forecast)"
        )
        click.echo("Preview only. Database unchanged; no backup created.")
        click.echo("To slim: stop all database users, then repeat with --apply --offline.")
        return

    click.echo(f"Checkpoints deduplicated: {stats['rewritten']}; history deleted: 0")
    click.echo(f"Database file: {before['file_bytes'] / mib:.2f} -> {after['file_bytes'] / mib:.2f} MiB")
    click.echo(f"WAL: {before['wal_bytes'] / mib:.2f} -> {after['wal_bytes'] / mib:.2f} MiB")
    click.echo(f"Backup: {backup} ({report['backup_bytes'] / mib:.2f} MiB; retained separately)")
    click.echo("Done. Keep the backup until the migrated database is verified.")
