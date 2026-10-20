"""Checkpoint growth optimization and explicit offline historical migration."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import click

from octop_memory.application.checkpoint_maintenance import maintain_checkpoints


@click.command(name="checkpoints")
@click.option("--apply", is_flag=True, help="Apply migration; default only inspects the existing file.")
@click.option("--offline", is_flag=True, help="Confirm ALL processes using this database are stopped.")
@click.option(
    "--backup", type=click.Path(path_type=Path, dir_okay=False), help="New full SQLite backup; required to apply."
)
@click.option(
    "--expand", is_flag=True, help="Restore inline encoding for old-reader rollback, without history pruning."
)
@click.option("--batch-size", type=click.IntRange(1, 1000), default=100, show_default=True)
@click.option(
    "--completed-thread",
    "completed_threads",
    multiple=True,
    help="Explicitly approve a completed thread for retention.",
)
@click.option(
    "--keep-last", type=click.IntRange(min=1), help="Keep N latest plus full dependency closure; no default deletion."
)
@click.option(
    "--protect-checkpoint",
    "protected_ids",
    multiple=True,
    help="Checkpoint ID referenced outside the saver; repeat for all external references.",
)
@click.option(
    "--vacuum", is_flag=True, help="Rebuild the file after migration; requires the offline window and free disk space."
)
@click.pass_context
def checkpoints_cmd(
    ctx: click.Context,
    apply: bool,
    offline: bool,
    backup: Path | None,
    expand: bool,
    batch_size: int,
    completed_threads: tuple[str, ...],
    keep_last: int | None,
    protected_ids: tuple[str, ...],
    vacuum: bool,
) -> None:
    """Inspect/migrate checkpoint fields in --db (SQLite only).

    Phase 1 is enabled for new Memory writes by default. This command is phase 2:
    migrate existing checkpoints, optionally prune approved completed threads,
    and reclaim file space. It never boots Memory, an agent or GC timers.

    Before pruning, the host must verify history projections and supply ALL
    external checkpoint references. Subgraphs and unprovable delta boundaries
    are skipped. --offline is an operator assertion, not an automatic service stop.
    """
    try:
        result = maintain_checkpoints(
            Path(ctx.obj["db"]),
            backend=ctx.obj["backend"],
            apply=apply,
            offline=offline,
            backup=backup,
            expand=expand,
            batch_size=batch_size,
            completed_threads=completed_threads,
            keep_last=keep_last,
            protected_ids=protected_ids,
            vacuum=vacuum,
        )
    except (ValueError, OSError, sqlite3.Error, ImportError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))
