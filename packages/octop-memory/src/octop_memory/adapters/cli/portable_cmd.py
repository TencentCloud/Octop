"""octop-memory portable subcommand group (requirements 1-5).

Provides four subcommands:
  octop-memory portable list-sources [--json]
  octop-memory portable pack --from <host>:<name> [--out <file>]
  octop-memory portable adopt <file>.hmpkg --as <host>[:<ns>] [--on-conflict ...] [--dry-run] [--host-rewrite ...]
  octop-memory portable doctor --host <host>[:<ns>] [--compare-with <pkg>]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click


@click.group(name="portable")
def portable_group() -> None:
    """Cross-host memory migration service: pack, adopt, doctor."""
    pass


# ---------------------------------------------------------------------------
# list-sources
# ---------------------------------------------------------------------------


@portable_group.command(name="list-sources")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output in JSON format.")
def list_sources_cmd(output_json: bool) -> None:
    """List every migratable memory store on this machine.

    Scans ~/.octop/agents/*/memory.sqlite, ~/.octop-harness/*/memory.sqlite,
    ~/.hermes/octopmemory/memory.sqlite, ~/.octopmemory/*/memory.sqlite.
    """
    from octop_memory.operations.migration.portable import list_sources

    sources = list_sources()

    if output_json:
        click.echo(json.dumps([s.to_dict() for s in sources], indent=2, ensure_ascii=False))
        return

    if not sources:
        click.echo("No migratable memory stores were found.")
        return

    click.echo(f"Found {len(sources)} memory store(s):\n")
    for i, src in enumerate(sources, 1):
        click.echo(f"  [{i}] {src.host_kind}:{src.agent_name or src.namespace}")
        click.echo(f"      namespace:   {src.namespace}")
        click.echo(f"      db_path:     {src.db_path}")
        click.echo(
            f"      counts:      raw_events={src.raw_event_count}  "
            f"atoms={src.atom_count}  entities={src.entity_count}  "
            f"journal={src.journal_count}"
        )
        click.echo(f"      schema_ver:  {src.schema_version}")
        click.echo()


# ---------------------------------------------------------------------------
# pack
# ---------------------------------------------------------------------------


@portable_group.command(name="pack")
@click.option(
    "--from",
    "source",
    required=True,
    help="Source memory store, format: host:name (e.g. agent:my-agent).",
)
@click.option(
    "--out",
    "out_path",
    default=None,
    type=click.Path(),
    help="Output file path (default: ~/.octop-memory/portable/<ns>-<ts>.hmpkg).",
)
def pack_cmd(source: str, out_path: str | None) -> None:
    """Pack the specified agent's memory into a .hmpkg file.

    Example: octop-memory portable pack --from agent:my-agent
    """
    from octop_memory.operations.migration.portable import pack

    def _progress(done: int, total: int, phase: str) -> None:
        if phase == "exporting":
            click.echo("  Exporting memory...", err=True)
        elif phase == "packing":
            click.echo("  Packing...", err=True)

    try:
        summary = pack(source, out=Path(out_path) if out_path else None, progress=_progress)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    size_kb = summary.file_size_bytes / 1024
    click.echo(
        f"packed {summary.total_rows} rows from {summary.source_namespace} -> {summary.out_path} ({size_kb:.1f} KB)"
    )


# ---------------------------------------------------------------------------
# adopt
# ---------------------------------------------------------------------------


@portable_group.command(name="adopt")
@click.argument("pkg_file", type=click.Path(exists=True))
@click.option(
    "--as",
    "target_host",
    required=True,
    help=(
        "Target host, format: host or host:namespace (e.g. openclaw or openclaw:myns). "
        "For openclaw without an explicit namespace, the namespace configured in "
        "~/.openclaw/openclaw.json (the one the plugin actually reads) is used when present."
    ),
)
@click.option(
    "--on-conflict",
    "on_conflict",
    default="skip",
    type=click.Choice(["skip", "replace", "raise"], case_sensitive=False),
    help="Conflict strategy (default: skip).",
)
@click.option(
    "--host-rewrite",
    "host_rewrite",
    default="keep",
    type=click.Choice(["keep", "target"], case_sensitive=False),
    help="Host-field rewrite strategy (default: keep, preserves the original host).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Pre-check only, without actually writing to the target db.",
)
def adopt_cmd(
    pkg_file: str,
    target_host: str,
    on_conflict: str,
    host_rewrite: str,
    dry_run: bool,
) -> None:
    """Import a .hmpkg file into the target host.

    Example: octop-memory portable adopt my-agent.hmpkg --as openclaw
    """
    from octop_memory.operations.migration.portable import adopt

    def _progress(done: int, total: int, phase: str) -> None:
        if phase == "importing":
            click.echo("  Importing memory...", err=True)

    try:
        summary = adopt(
            pkg_file,
            target_host,
            on_conflict=on_conflict,  # type: ignore[arg-type]
            host_rewrite=host_rewrite,  # type: ignore[arg-type]
            dry_run=dry_run,
            progress=_progress,
        )
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if summary.already_adopted:
        click.echo(f"already adopted at {summary.already_adopted_at}, skipping.")
        return

    if dry_run:
        click.echo(
            f"[dry-run] would write approximately {summary.applied} record(s) -> "
            f"{summary.target_namespace} ({summary.target_db_path})"
        )
        return

    click.echo(
        f"adopted: {summary.applied} inserted, {summary.skipped} skipped"
        + (f", {len(summary.errors)} errors" if summary.errors else "")
        + f" -> {summary.target_namespace} ({summary.target_db_path})"
    )
    if summary.errors:
        for err in summary.errors[:5]:
            click.echo(f"  error: {err}", err=True)
        if len(summary.errors) > 5:
            click.echo(f"  ... {len(summary.errors)} errors in total", err=True)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@portable_group.command(name="doctor")
@click.option(
    "--host",
    "host_spec",
    required=True,
    help=(
        "Target host, format: host or host:namespace (e.g. openclaw:myns). "
        "For openclaw without an explicit namespace, the plugin's configured "
        "namespace from ~/.openclaw/openclaw.json is used when present."
    ),
)
@click.option(
    "--compare-with",
    "compare_with",
    default=None,
    type=click.Path(exists=True),
    help="Compare row counts against the manifest of the given .hmpkg file.",
)
@click.option(
    "--db",
    "db_path",
    default=None,
    type=click.Path(),
    help="Directly specify the db path (overrides auto-resolution).",
)
@click.option("--json", "output_json", is_flag=True, default=False, help="Output in JSON format.")
def doctor_cmd(
    host_spec: str,
    compare_with: str | None,
    db_path: str | None,
    output_json: bool,
) -> None:
    """Check the health status of the target db.

    Example: octop-memory portable doctor --host openclaw:myns --compare-with my-agent.hmpkg
    """
    from octop_memory.operations.migration.portable import doctor

    report = doctor(
        host_spec,
        compare_with=Path(compare_with) if compare_with else None,
        db_path=db_path,
    )

    if output_json:
        click.echo(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        sys.exit(0 if report.all_passed else 1)

    # Human-readable output
    click.echo(f"\n\U0001f50d doctor report: {report.host_kind}:{report.namespace}")
    click.echo(f"   db: {report.db_path}")
    click.echo(
        f"   counts: raw_events={report.raw_event_count}  "
        f"atoms={report.atom_count}  entities={report.entity_count}  "
        f"journal={report.journal_count}"
    )
    click.echo()

    for check in report.checks:
        icon = "\u2713" if check.passed else "\u2717"
        line = f"  {icon} {check.name}"
        if check.detail:
            line += f"  ({check.detail})"
        click.echo(line)
        if not check.passed and check.hint:
            click.echo(f"    -> {check.hint}", err=True)

    click.echo()
    if report.all_passed:
        click.echo("\u2705 all checks passed")
    else:
        failed = [c.name for c in report.checks if not c.passed]
        click.echo(f"\u274c {len(failed)} check(s) failed: {', '.join(failed)}", err=True)
        sys.exit(1)


__all__ = ["portable_group"]
