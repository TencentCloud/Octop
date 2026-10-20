"""Memory CLI ``thread`` subcommand.

Memory CLI: ``thread`` subcommand for inspecting active-entity stack (M4)
and pruning checkpoint history (checkpointer sqlite growth management)."""

from __future__ import annotations

import json
from typing import Any

import click

from octop_memory.adapters.cli.config import get_memory
from octop_memory.pipeline.lifecycle.checkpoint_gc import (
    DEFAULT_KEEP_LAST_CHECKPOINTS,
    CheckpointGcStats,
    prune_checkpoints,
)


@click.group(name="thread")
def thread_group() -> None:
    """Inspect thread-scoped state (active-entity stack)."""


@thread_group.command(name="show")
@click.argument("thread_id")
@click.option("--limit", default=5, show_default=True, type=int)
@click.pass_context
def show_cmd(ctx: click.Context, thread_id: str, limit: int) -> None:
    """Show the active-entity LRU stack for THREAD_ID."""
    memory = get_memory(ctx)
    rows = memory.list_active_entities(thread_id, limit=limit)

    if ctx.obj.get("output_json"):
        payload: list[dict[str, Any]] = [
            {
                "thread_id": r.thread_id,
                "entity_id": r.entity_id,
                "last_seen_at": r.last_seen_at.isoformat(),
                "source": r.source,
            }
            for r in rows
        ]
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not rows:
        click.echo(f"(no active entities for thread {thread_id})")
        return

    click.echo(f"thread_id: {thread_id}")
    click.echo("")
    for idx, row in enumerate(rows, 1):
        entity = memory.get_entity(row.entity_id)
        name = entity.canonical_name if entity else "(unknown)"
        click.echo(f"{idx}. {row.entity_id[:12]}  {name}  ({row.source})  last_seen={row.last_seen_at.isoformat()}")


@thread_group.command(name="prune")
@click.option(
    "--thread-id",
    default=None,
    help="Prune only this thread. Default: scan every thread in the checkpointer.",
)
@click.option(
    "--keep-last",
    default=DEFAULT_KEEP_LAST_CHECKPOINTS,
    show_default=True,
    type=int,
    help="Always keep the newest N checkpoints per thread, regardless of age. "
    "Pass 0 to disable this check and rely on --keep-days alone.",
)
@click.option(
    "--keep-days",
    default=None,
    type=int,
    help="Always keep checkpoints newer than this many days, regardless of rank. "
    "Combined with --keep-last via OR (a checkpoint is deleted only if it fails both).",
)
@click.option(
    "--drop-subgraph-streams",
    is_flag=True,
    default=False,
    help="Delete finished tools:* / subgraph streams. Skips in-flight and HITL threads.",
)
@click.option(
    "--force-drop-subgraphs",
    is_flag=True,
    default=False,
    help="With --drop-subgraph-streams, delete subgraphs even if the parent looks in-flight.",
)
@click.option("--dry-run", is_flag=True, default=False, help="Count what WOULD be deleted without modifying anything.")
@click.pass_context
def prune_cmd(
    ctx: click.Context,
    thread_id: str | None,
    keep_last: int,
    keep_days: int | None,
    drop_subgraph_streams: bool,
    force_drop_subgraphs: bool,
    dry_run: bool,
) -> None:
    """Shrink the checkpointer's ``checkpoints``/``writes`` tables.

    LangGraph's SqliteSaver never deletes old checkpoints on its own —
    every graph step keeps a full-state row forever. This trims each
    thread down to its newest --keep-last parent checkpoint and/or the
    last --keep-days days, without deleting the thread itself.
    """
    memory = get_memory(ctx)
    effective_keep_last = keep_last if keep_last > 0 else None
    stats = prune_checkpoints(
        memory,
        keep_last=effective_keep_last,
        keep_days=keep_days,
        thread_id=thread_id,
        drop_subgraph_streams=drop_subgraph_streams or force_drop_subgraphs,
        force_drop_subgraphs=force_drop_subgraphs,
        dry_run=dry_run,
    )

    if ctx.obj.get("output_json"):
        click.echo(_stats_to_json(stats))
        return

    label = "(dry run) would delete" if stats.dry_run else "deleted"
    click.echo(f"threads_scanned      : {stats.threads_scanned}")
    click.echo(f"streams_scanned      : {stats.streams_scanned}")
    click.echo(f"streams_dropped      : {stats.streams_dropped}")
    click.echo(f"{label} checkpoints  : {stats.checkpoints_deleted}")
    click.echo(f"{label} writes       : {stats.writes_deleted}")


def _stats_to_json(stats: CheckpointGcStats) -> str:
    return json.dumps(
        {
            "dry_run": stats.dry_run,
            "threads_scanned": stats.threads_scanned,
            "streams_scanned": stats.streams_scanned,
            "streams_dropped": stats.streams_dropped,
            "checkpoints_deleted": stats.checkpoints_deleted,
            "writes_deleted": stats.writes_deleted,
            "started_at": stats.started_at.isoformat() if stats.started_at else None,
            "finished_at": stats.finished_at.isoformat() if stats.finished_at else None,
        },
        ensure_ascii=False,
        indent=2,
    )


__all__ = ["thread_group"]
