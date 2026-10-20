"""Memory CLI: ``gc`` subcommand (M5.6, D47-C cron + manual)."""

from __future__ import annotations

import json

import click

from octop_memory.adapters.cli.config import get_memory
from octop_memory.pipeline.lifecycle.gc import (
    DEFAULT_DEPRECATED_ATOM_DAYS,
    DEFAULT_JOURNAL_PIPELINE_DAYS,
    DEFAULT_MAX_ROWS_PER_PASS,
    DEFAULT_ORPHAN_RAW_DAYS,
    DEFAULT_REJECTED_CANDIDATE_DAYS,
    GcStats,
    run_gc,
)


@click.group(name="gc")
def gc_group() -> None:
    """Lifecycle GC (manual or scheduler-driven, D47-C)."""


@gc_group.command(name="run")
@click.option("--rejected-days", default=DEFAULT_REJECTED_CANDIDATE_DAYS, show_default=True, type=int)
@click.option("--deprecated-atom-days", default=DEFAULT_DEPRECATED_ATOM_DAYS, show_default=True, type=int)
@click.option("--orphan-raw-days", default=DEFAULT_ORPHAN_RAW_DAYS, show_default=True, type=int)
@click.option(
    "--journal-days",
    default=DEFAULT_JOURNAL_PIPELINE_DAYS,
    show_default=True,
    type=int,
    help="Retention for extract_run / gc_* / page_regen / consolidate journal rows.",
)
@click.option(
    "--max-rows",
    default=DEFAULT_MAX_ROWS_PER_PASS,
    show_default=True,
    type=int,
    help="Per-pass row cap so a single tick can't lock the database.",
)
@click.option("--dry-run", is_flag=True, default=False, help="Count what WOULD be deleted without modifying anything.")
@click.pass_context
def run_cmd(
    ctx: click.Context,
    rejected_days: int,
    deprecated_atom_days: int,
    orphan_raw_days: int,
    journal_days: int,
    max_rows: int,
    dry_run: bool,
) -> None:
    """Run a single GC pass over the active namespace."""
    memory = get_memory(ctx)
    stats = run_gc(
        memory,
        rejected_candidate_days=rejected_days,
        deprecated_atom_days=deprecated_atom_days,
        orphan_raw_days=orphan_raw_days,
        journal_pipeline_days=journal_days,
        max_rows_per_pass=max_rows,
        dry_run=dry_run,
    )

    if ctx.obj.get("output_json"):
        click.echo(_stats_to_json(stats))
        return

    label = "(dry run) would delete" if stats.dry_run else "deleted"
    click.echo(f"{label}:")
    click.echo(f"  rejected_candidates : {stats.rejected_candidates_deleted}")
    click.echo(f"  deprecated_atoms    : {stats.deprecated_atoms_deleted}")
    click.echo(f"  orphan_raw_events   : {stats.orphan_raw_events_deleted}")
    click.echo(f"  journal_rows        : {stats.journal_rows_deleted}")
    click.echo(f"  total               : {stats.total_deleted}")


def _stats_to_json(stats: GcStats) -> str:
    return json.dumps(
        {
            "dry_run": stats.dry_run,
            "rejected_candidates_deleted": stats.rejected_candidates_deleted,
            "deprecated_atoms_deleted": stats.deprecated_atoms_deleted,
            "orphan_raw_events_deleted": stats.orphan_raw_events_deleted,
            "journal_rows_deleted": stats.journal_rows_deleted,
            "total_deleted": stats.total_deleted,
            "started_at": stats.started_at.isoformat() if stats.started_at else None,
            "finished_at": stats.finished_at.isoformat() if stats.finished_at else None,
        },
        ensure_ascii=False,
        indent=2,
    )


__all__ = ["gc_group"]
