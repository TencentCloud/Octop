"""Memory CLI: ``consolidate`` subcommand (intra-entity semantic dedup).

Sibling of ``gc``: a bounded, dry-run-able lifecycle pass that scans each
entity's live atoms and deprecates paraphrase duplicates (keeping the
best one). Without ``--dev-llm`` only high-Jaccard near-duplicates merge;
with a dev LLM the grey-zone paraphrases get confirmed too.
"""

from __future__ import annotations

import json

import click

from octop_memory.adapters.cli.candidate_cmd import _parse_dev_llm
from octop_memory.adapters.cli.config import get_memory
from octop_memory.pipeline.lifecycle.consolidate import (
    DEFAULT_JACCARD_PREFILTER,
    DEFAULT_MAX_ENTITIES,
    DEFAULT_MAX_LLM_CALLS,
    DEFAULT_MIN_ATOMS,
    ConsolidationStats,
    DuplicateCluster,
    run_consolidation,
)
from octop_memory.pipeline.promotion.llm_hook import ModelEscalationHook


@click.group(name="consolidate")
def consolidate_group() -> None:
    """Intra-entity semantic dedup (manual or scheduler-driven)."""


@consolidate_group.command(name="run")
@click.option("--entity-type", default=None, help="Limit to one entity type (default: all).")
@click.option("--min-atoms", default=DEFAULT_MIN_ATOMS, show_default=True, type=int)
@click.option("--jaccard", "jaccard_prefilter", default=DEFAULT_JACCARD_PREFILTER, show_default=True, type=float)
@click.option("--max-entities", default=DEFAULT_MAX_ENTITIES, show_default=True, type=int)
@click.option("--max-llm-calls", default=DEFAULT_MAX_LLM_CALLS, show_default=True, type=int)
@click.option("--dry-run", is_flag=True, default=False, help="Count what WOULD be merged without modifying anything.")
@click.option(
    "--dev-llm",
    "dev_llm",
    default=None,
    help=(
        "(dev-only) confirm grey-zone paraphrase duplicates with this LLM. "
        "Format: 'ollama:<model>' or 'remote:<base_url>:<model>'. "
        "Without it only high-Jaccard near-duplicates are merged (no LLM calls)."
    ),
)
@click.pass_context
def run_cmd(
    ctx: click.Context,
    entity_type: str | None,
    min_atoms: int,
    jaccard_prefilter: float,
    max_entities: int,
    max_llm_calls: int,
    dry_run: bool,
    dev_llm: str | None,
) -> None:
    """Run a single consolidation pass over the active namespace."""
    memory = get_memory(ctx)

    llm_hook = ModelEscalationHook(_parse_dev_llm(dev_llm)) if dev_llm else None

    as_json = ctx.obj.get("output_json")
    clusters: list[DuplicateCluster] = []

    stats = run_consolidation(
        memory,
        llm_hook=llm_hook,
        entity_type=entity_type,
        min_atoms=min_atoms,
        jaccard_prefilter=jaccard_prefilter,
        max_entities=max_entities,
        max_llm_calls=max_llm_calls,
        dry_run=dry_run,
        # Collect for human output; skip the bookkeeping in --json mode.
        on_cluster=(None if as_json else clusters.append),
    )

    if as_json:
        click.echo(_stats_to_json(stats))
        return

    verb = "would merge" if stats.dry_run else "merged"
    for cluster in clusters:
        click.echo(
            f"[{cluster.entity_id[:8]}] {verb} {len(cluster.losers)} "
            f"→ keep {cluster.keeper_id[:8]} ({cluster.confirmed_by})"
        )
        click.echo(f"    keep: {cluster.keeper_assertion}")
        for loser_id, loser_assertion in cluster.losers:
            click.echo(f"    drop {loser_id[:8]}: {loser_assertion}")

    label = "(dry run) would deprecate" if stats.dry_run else "deprecated"
    click.echo(f"{label}:")
    click.echo(f"  entities_scanned        : {stats.entities_scanned}")
    click.echo(f"  duplicate_clusters_found: {stats.duplicate_clusters_found}")
    click.echo(f"  atoms_deprecated        : {stats.atoms_deprecated}")
    click.echo(f"  llm_calls               : {stats.llm_calls}")
    click.echo(f"  journal_rows_added      : {stats.journal_rows_added}")


def _stats_to_json(stats: ConsolidationStats) -> str:
    return json.dumps(
        {
            "dry_run": stats.dry_run,
            "entities_scanned": stats.entities_scanned,
            "duplicate_clusters_found": stats.duplicate_clusters_found,
            "atoms_deprecated": stats.atoms_deprecated,
            "llm_calls": stats.llm_calls,
            "journal_rows_added": stats.journal_rows_added,
            "started_at": stats.started_at.isoformat() if stats.started_at else None,
            "finished_at": stats.finished_at.isoformat() if stats.finished_at else None,
        },
        ensure_ascii=False,
        indent=2,
    )


__all__ = ["consolidate_group"]
