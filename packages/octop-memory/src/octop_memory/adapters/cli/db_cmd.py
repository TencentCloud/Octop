"""Memory CLI: ``db`` subcommand (storage-level maintenance, RISK-026 / ADR-025).

Distinct from ``octop-memory gc`` (which cleans up business rows — candidates,
atoms, raw events) and ``octop-memory thread prune`` (LangGraph checkpoint
retention): this group reclaims the disk space those cleanups free up,
which neither backend does automatically on its own for the tables that
matter here. See ``pipeline/lifecycle/vacuum.py`` for the full design
rationale (SQLite vs Postgres are genuinely different stories).

Three space-reclamation commands, deliberately split by *what they cost* rather than by
backend:

* ``check``   — read-only, always safe. The inspection entry point.
* ``vacuum``  — cheap, bounded, safe with live traffic.
* ``compact`` — heavy, holds an exclusive lock, needs a real idle window.

``checkpoints`` handles checkpoint field deduplication and migration;
``slim DATABASE`` is its lossless shortcut with automatic backup and VACUUM.

``check`` is its own command rather than a ``--dry-run`` flag on the
other two (ADR-025): inspecting storage health is a first-class thing
users want to do on its own, and it reports more than any single
operation's preview could — current size, wasted space, per-table dead
tuples on Postgres, plus concrete recommendations.
"""

from __future__ import annotations

import json

import click

from octop_memory.adapters.cli.checkpoint_cmd import checkpoints_cmd
from octop_memory.adapters.cli.config import get_memory
from octop_memory.adapters.cli.slim_cmd import slim_cmd
from octop_memory.pipeline.lifecycle.vacuum import (
    DEFAULT_INCREMENTAL_VACUUM_PAGES,
    CompactStats,
    StorageCheck,
    VacuumStats,
    check_storage,
    compact_vacuum,
    nudge_vacuum,
)


@click.group(name="db")
def db_group() -> None:
    """Inspect storage, deduplicate checkpoint fields, and reclaim file space."""


db_group.add_command(checkpoints_cmd)
db_group.add_command(slim_cmd)


@db_group.command(name="check")
@click.pass_context
def check_cmd(ctx: click.Context) -> None:
    """Read-only storage health report — never modifies anything.

    Shows how much space is currently wasted, what `octop-memory db vacuum`
    would reclaim right now, and what to do next. Safe to run any time,
    including from monitoring (pair with the global --json flag).
    """
    memory = get_memory(ctx)
    check = check_storage(memory)

    if ctx.obj.get("output_json"):
        click.echo(_check_to_json(check))
        return

    _print_check(check)


@db_group.command(name="vacuum")
@click.option(
    "--pages",
    default=DEFAULT_INCREMENTAL_VACUUM_PAGES,
    show_default=True,
    type=int,
    help="SQLite only: max pages to reclaim per call via PRAGMA incremental_vacuum. Ignored on Postgres.",
)
@click.pass_context
def vacuum_cmd(ctx: click.Context, pages: int) -> None:
    """Cheap, bounded reclaim — safe to run with live traffic.

    SQLite: PRAGMA incremental_vacuum in small batches (requires
    auto_vacuum=INCREMENTAL to already be on — run `octop-memory db compact`
    once first if it isn't; `octop-memory db check` tells you). Postgres: a
    plain, non-blocking VACUUM on journal + the LangGraph checkpoint
    tables, nudging autovacuum along. Safe to schedule frequently (e.g.
    from a host's idle timer) on either backend.

    Use `octop-memory db check` to preview what this would reclaim.
    """
    memory = get_memory(ctx)
    stats = nudge_vacuum(memory, pages=pages)

    if ctx.obj.get("output_json"):
        click.echo(_vacuum_stats_to_json(stats))
        return

    _print_vacuum_stats(stats)


@db_group.command(name="compact")
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help=(
        "Required: confirms you've checked for a safe idle window. "
        "This holds an exclusive lock — SQLite: blocks writers for the whole rebuild; "
        "Postgres: VACUUM FULL blocks reads AND writes, on tables shared by every "
        "namespace on the instance. Not something to schedule blindly — see ADR-025. "
        "Run `octop-memory db check` first to see whether it's worth the cost."
    ),
)
@click.pass_context
def compact_cmd(ctx: click.Context, yes: bool) -> None:
    """Heavy, exclusive-lock reclaim — only run during a confirmed idle window.

    SQLite: a full VACUUM (also bootstraps auto_vacuum=INCREMENTAL the
    first time it's run, so `octop-memory db vacuum` starts working after
    this). Postgres: VACUUM FULL per table. Treat this as a manual,
    ops-invoked operation — do not wire it into an automatic schedule
    without the safeguards described in ADR-025.

    Use `octop-memory db check` to preview the current size first.
    """
    if not yes:
        raise click.UsageError(
            "octop-memory db compact holds an exclusive lock (see --help). "
            "Pass --yes to confirm you've checked for a safe idle window, "
            "or run `octop-memory db check` to inspect without modifying anything."
        )
    memory = get_memory(ctx)
    stats = compact_vacuum(memory)

    if ctx.obj.get("output_json"):
        click.echo(_compact_stats_to_json(stats))
        return

    _print_compact_stats(stats)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _print_check(check: StorageCheck) -> None:
    click.echo(f"backend: {check.backend}")
    if check.backend == "sqlite":
        click.echo(f"  auto_vacuum          : {'INCREMENTAL' if check.auto_vacuum_enabled else 'NONE (not enabled)'}")
        click.echo(f"  file_size            : {check.file_size} bytes")
        click.echo(f"  wal_size             : {check.wal_size} bytes")
        click.echo(f"  page_size            : {check.page_size} bytes")
        click.echo(f"  total_pages          : {check.total_pages}")
        click.echo(f"  free_pages           : {check.freelist_pages}")
        click.echo(f"  reclaimable          : {check.reclaimable_bytes} bytes")
        click.echo(f"  `db vacuum` would reclaim: {check.would_reclaim_pages} pages")
    else:
        for t in check.tables:
            if not t.exists:
                click.echo(f"  {t.table:<32} (does not exist)")
                continue
            click.echo(
                f"  {t.table:<32} live={t.live_tuples} dead={t.dead_tuples} "
                f"last_vacuum={t.last_vacuum or '-'} last_autovacuum={t.last_autovacuum or '-'}"
            )
    if check.recommendations:
        click.echo("\nrecommendations:")
        for rec in check.recommendations:
            click.echo(f"  - {rec}")


def _print_vacuum_stats(stats: VacuumStats) -> None:
    click.echo(f"backend: {stats.backend}")
    if stats.backend == "sqlite":
        if stats.skipped_reason:
            click.echo(f"  skipped: {stats.skipped_reason} — retry when the store is idle.")
        elif stats.auto_vacuum_enabled is False:
            click.echo("  auto_vacuum is not INCREMENTAL yet — run `octop-memory db compact --yes` once first.")
        click.echo(f"  freelist_pages_before : {stats.freelist_pages_before}")
        click.echo(f"  pages_reclaimed       : {stats.pages_reclaimed}")
    else:
        for t in stats.tables:
            detail = f" ({t.skipped_reason})" if t.skipped_reason else ""
            click.echo(f"  {t.table:<32} {t.action}{detail}")


def _print_compact_stats(stats: CompactStats) -> None:
    click.echo(f"backend: {stats.backend}")
    if stats.file_size_before is not None and stats.file_size_after is not None:
        click.echo(f"  file_size_before : {stats.file_size_before}")
        click.echo(f"  file_size_after  : {stats.file_size_after}")
        click.echo(f"  reclaimed        : {stats.file_size_before - stats.file_size_after} bytes")
    for t in stats.tables:
        detail = f" ({t.skipped_reason})" if t.skipped_reason else ""
        click.echo(f"  {t.table:<32} {t.action}{detail}")


def _check_to_json(check: StorageCheck) -> str:
    return json.dumps(
        {
            "backend": check.backend,
            "auto_vacuum_enabled": check.auto_vacuum_enabled,
            "page_size": check.page_size,
            "total_pages": check.total_pages,
            "freelist_pages": check.freelist_pages,
            "reclaimable_bytes": check.reclaimable_bytes,
            "would_reclaim_pages": check.would_reclaim_pages,
            "file_size": check.file_size,
            "wal_size": check.wal_size,
            "tables": [
                {
                    "table": t.table,
                    "exists": t.exists,
                    "live_tuples": t.live_tuples,
                    "dead_tuples": t.dead_tuples,
                    "last_vacuum": t.last_vacuum,
                    "last_autovacuum": t.last_autovacuum,
                }
                for t in check.tables
            ],
            "recommendations": check.recommendations,
        }
    )


def _vacuum_stats_to_json(stats: VacuumStats) -> str:
    return json.dumps(
        {
            "backend": stats.backend,
            "dry_run": stats.dry_run,
            "auto_vacuum_enabled": stats.auto_vacuum_enabled,
            "freelist_pages_before": stats.freelist_pages_before,
            "pages_reclaimed": stats.pages_reclaimed,
            "skipped_reason": stats.skipped_reason,
            "tables": [
                {"table": t.table, "action": t.action, "skipped_reason": t.skipped_reason} for t in stats.tables
            ],
        }
    )


def _compact_stats_to_json(stats: CompactStats) -> str:
    return json.dumps(
        {
            "backend": stats.backend,
            "dry_run": stats.dry_run,
            "file_size_before": stats.file_size_before,
            "file_size_after": stats.file_size_after,
            "reclaimed_bytes": (
                None
                if stats.file_size_before is None or stats.file_size_after is None
                else stats.file_size_before - stats.file_size_after
            ),
            "auto_vacuum_was_enabled": stats.auto_vacuum_was_enabled,
            "tables": [
                {"table": t.table, "action": t.action, "skipped_reason": t.skipped_reason} for t in stats.tables
            ],
        }
    )


__all__ = ["db_group"]
