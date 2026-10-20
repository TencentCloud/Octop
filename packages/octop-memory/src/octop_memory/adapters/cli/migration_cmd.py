"""Memory CLI: ``export`` / ``import`` / ``migrate`` / ``backfill`` (M5.9).

All four belong to the migration / data-management family and share a
single click group ``migration_cmd`` exposed at top level so users
type ``memory export`` / ``memory import`` etc. (no nesting under
``memory migration``).

Each subcommand is a thin wrapper around the corresponding
``migration.*`` module.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import click

from octop_memory.adapters.cli.candidate_cmd import _parse_dev_llm
from octop_memory.adapters.cli.config import get_memory
from octop_memory.operations.migration.backfill import (
    DEFAULT_RATE_LIMIT_PER_MINUTE,
    BackfillSummary,
    backfill_namespace,
)
from octop_memory.operations.migration.export import ExportSummary, export_namespace
from octop_memory.operations.migration.import_ import (
    ImportSummary,
    OnConflict,
    import_namespace,
)
from octop_memory.operations.migration.preview import render_rename_plan
from octop_memory.operations.migration.rename import apply_rename, plan_rename
from octop_memory.pipeline.extractor import CandidateExtractor

ERROR_PREVIEW_LIMIT = 20
"""Max number of error lines shown in the import summary CLI output."""

# ---------------------------------------------------------------------------
# memory export
# ---------------------------------------------------------------------------


@click.command(name="export")
@click.option("--out", "out_path", required=True, type=click.Path(dir_okay=False, path_type=Path))
@click.option("--gzip", "gzip_compress", is_flag=True, default=False, help="Compress output with gzip.")
@click.pass_context
def export_cmd(ctx: click.Context, out_path: Path, gzip_compress: bool) -> None:
    """Export the active namespace to a JSONL file (D50-C)."""
    memory = get_memory(ctx)
    summary = export_namespace(memory, out_path, gzip_compress=gzip_compress)
    if ctx.obj.get("output_json"):
        click.echo(_export_summary_to_json(summary))
        return
    click.echo(f"exported namespace {summary.namespace} → {summary.out_path}")
    click.echo(f"total rows : {summary.total_rows}")
    for table, count in summary.counts.items():
        if count:
            click.echo(f"  {table:<28} {count}")


def _export_summary_to_json(summary: ExportSummary) -> str:
    return json.dumps(
        {
            "namespace": summary.namespace,
            "out_path": str(summary.out_path),
            "total_rows": summary.total_rows,
            "counts": summary.counts,
            "started_at": summary.started_at.isoformat(),
            "finished_at": summary.finished_at.isoformat() if summary.finished_at else None,
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# memory import
# ---------------------------------------------------------------------------


@click.command(name="import")
@click.option("--from", "in_path", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--on-conflict",
    type=click.Choice(["skip", "replace", "raise"]),
    default="skip",
    show_default=True,
    help=(
        "Conflict policy when a row's primary key already exists. "
        "'skip' (default): keep existing row, count as skipped. "
        "'replace': currently behaves the same as 'skip' — "
        "full upsert semantics are not yet implemented for most tables "
        "(entity_pages is the exception). "
        "'raise': abort on first conflict."
    ),
)
@click.option("--expect-namespace", default=None, help="Refuse the import if the dump's namespace doesn't match.")
@click.pass_context
def import_cmd(
    ctx: click.Context,
    in_path: Path,
    on_conflict: OnConflict,
    expect_namespace: str | None,
) -> None:
    """Import a JSONL dump into the active namespace."""
    memory = get_memory(ctx)
    if on_conflict == "replace" and not ctx.obj.get("output_json"):
        click.echo(
            "Warning: --on-conflict replace currently behaves the same as 'skip' "
            "for most tables (entity_pages is the exception). "
            "Existing rows will NOT be overwritten.",
            err=True,
        )
    summary = import_namespace(
        memory,
        in_path,
        on_conflict=on_conflict,
        expect_namespace=expect_namespace,
    )
    if ctx.obj.get("output_json"):
        click.echo(_import_summary_to_json(summary))
        return
    click.echo(f"imported {summary.total_applied} rows into namespace {memory.namespace}")
    if summary.applied:
        for table, count in sorted(summary.applied.items()):
            click.echo(f"  applied   {table:<28} {count}")
    if summary.skipped:
        for table, count in sorted(summary.skipped.items()):
            click.echo(f"  skipped   {table:<28} {count}")
    if summary.errors:
        click.echo("")
        click.echo(f"errors ({len(summary.errors)}):", err=True)
        for line in summary.errors[:ERROR_PREVIEW_LIMIT]:
            click.echo(f"  {line}", err=True)
        if len(summary.errors) > ERROR_PREVIEW_LIMIT:
            click.echo(f"  ... +{len(summary.errors) - ERROR_PREVIEW_LIMIT} more", err=True)


def _import_summary_to_json(summary: ImportSummary) -> str:
    return json.dumps(
        {
            "applied": summary.applied,
            "skipped": summary.skipped,
            "errors": summary.errors,
            "header": summary.header,
            "footer": summary.footer,
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# memory migrate (rename namespace, D49-C dual-format dry-run)
# ---------------------------------------------------------------------------


@click.command(name="migrate")
@click.option("--db", "db_path", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--from-namespace", "src_namespace", required=True)
@click.option("--to-namespace", "dst_namespace", required=True)
@click.option("--mode", type=click.Choice(["rename", "copy"]), default="rename", show_default=True)
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Preview only; do not modify the database.")
@click.option("--allow-overwrite", is_flag=True, default=False, help="Drop conflicting destination tables first.")
@click.option(
    "--report-json",
    "report_json",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write a structured JSON report of the plan to this path (D49-C).",
)
@click.pass_context
def migrate_cmd(
    ctx: click.Context,
    db_path: Path,
    src_namespace: str,
    dst_namespace: str,
    mode: str,
    dry_run: bool,
    allow_overwrite: bool,
    report_json: Path | None,
) -> None:
    """Rename or copy a namespace. Use ``--dry-run`` to preview first."""
    plan = plan_rename(
        db_path,
        src_namespace=src_namespace,
        dst_namespace=dst_namespace,
        mode=mode,  # type: ignore[arg-type]
    )

    text_report = render_rename_plan(plan, fmt="text")
    if report_json is not None:
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(render_rename_plan(plan, fmt="json"), encoding="utf-8")

    if ctx.obj.get("output_json"):
        click.echo(render_rename_plan(plan, fmt="json"))
    else:
        click.echo(text_report)

    if dry_run:
        return

    if plan.has_conflicts and not allow_overwrite:
        click.echo(
            "Refusing to apply: conflicts detected. Re-run with --allow-overwrite or pick a different target.",
            err=True,
        )
        sys.exit(1)
    if not plan.steps:
        return

    affected = apply_rename(plan, allow_overwrite=allow_overwrite)
    click.echo(f"applied: {affected} tables affected.")


# ---------------------------------------------------------------------------
# memory backfill (D48-B sliding-window rate limiter)
# ---------------------------------------------------------------------------


@click.command(name="backfill")
@click.option("--since", default=None, help="ISO datetime; lower bound on raw events to replay.")
@click.option(
    "--rate-limit",
    "rate_limit",
    default=f"{DEFAULT_RATE_LIMIT_PER_MINUTE}/min",
    show_default=True,
    help="Max LLM calls per minute. Format: 'N/min'. Set '0/min' to disable.",
)
@click.option(
    "--dev-llm",
    "dev_llm",
    default=None,
    help="Dev LLM client spec (matches `memory candidate extract`). Without it backfill skips real LLM calls.",
)
@click.option(
    "--resume-from",
    "resume_from",
    default=None,
    help="Skip every session up to and including this id (for retrying after interrupt).",
)
@click.option(
    "--no-promote",
    "no_promote",
    is_flag=True,
    default=False,
    help="Stop at candidate stage; don't run promotion.",
)
@click.pass_context
def backfill_cmd(
    ctx: click.Context,
    since: str | None,
    rate_limit: str,
    dev_llm: str | None,
    resume_from: str | None,
    no_promote: bool,
) -> None:
    """Replay the candidate extractor over historical raw events."""
    memory = get_memory(ctx)
    cutoff = _parse_iso(since) if since else None
    cap = _parse_rate_limit(rate_limit)
    llm = _parse_dev_llm(dev_llm)
    extractor = CandidateExtractor(llm=llm)

    summary = backfill_namespace(
        memory,
        extractor=extractor,
        since=cutoff,
        rate_limit_per_minute=cap,
        resume_from=resume_from,
        promote=not no_promote,
    )

    if ctx.obj.get("output_json"):
        click.echo(_backfill_summary_to_json(summary))
        return
    click.echo(f"sessions seen      : {summary.sessions_seen}")
    click.echo(f"sessions processed : {summary.sessions_processed}")
    click.echo(f"sessions skipped   : {summary.sessions_skipped}")
    click.echo(f"total candidates   : {summary.total_candidates}")
    click.echo(f"total promoted     : {summary.total_promoted}")
    click.echo(f"llm calls          : {summary.llm_calls}")


def _backfill_summary_to_json(summary: BackfillSummary) -> str:
    return json.dumps(
        {
            "sessions_seen": summary.sessions_seen,
            "sessions_processed": summary.sessions_processed,
            "sessions_skipped": summary.sessions_skipped,
            "total_candidates": summary.total_candidates,
            "total_promoted": summary.total_promoted,
            "llm_calls": summary.llm_calls,
            "started_at": summary.started_at.isoformat() if summary.started_at else None,
            "finished_at": summary.finished_at.isoformat() if summary.finished_at else None,
            "sessions": [
                {
                    "session_id": s.session_id,
                    "raw_event_count": s.raw_event_count,
                    "candidate_count": s.candidate_count,
                    "promoted_atom_count": s.promoted_atom_count,
                    "skipped_reason": s.skipped_reason,
                }
                for s in summary.sessions
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _parse_rate_limit(spec: str) -> int:
    """Parse 'N/min' into an integer cap. Tolerant of spaces."""
    token = spec.strip().lower().replace(" ", "")
    if token.endswith("/min"):
        return int(token[: -len("/min")])
    if token.isdigit():
        return int(token)
    raise click.BadParameter(f"--rate-limit must look like '30/min' (got {spec!r})")


__all__ = ["backfill_cmd", "export_cmd", "import_cmd", "migrate_cmd"]
