"""CLI entry point for octop-memory."""

from __future__ import annotations

from pathlib import Path

import click

from octop_memory import __version__
from octop_memory.adapters.cli.atom_cmd import atom_group
from octop_memory.adapters.cli.candidate_cmd import candidate_group
from octop_memory.adapters.cli.config import config_group, load_config, set_config_path
from octop_memory.adapters.cli.consolidate_cmd import consolidate_group
from octop_memory.adapters.cli.db_cmd import db_group
from octop_memory.adapters.cli.entity_cmd import entity_group
from octop_memory.adapters.cli.episode_cmd import digest_group, episode_group
from octop_memory.adapters.cli.gc_cmd import gc_group
from octop_memory.adapters.cli.journal_cmd import journal_group
from octop_memory.adapters.cli.memory_cmd import memory_group
from octop_memory.adapters.cli.migration_cmd import (
    backfill_cmd,
    export_cmd,
    import_cmd,
    migrate_cmd,
)
from octop_memory.adapters.cli.openclaw_cmd import openclaw_group
from octop_memory.adapters.cli.page_cmd import page_group
from octop_memory.adapters.cli.portable_cmd import portable_group
from octop_memory.adapters.cli.raw_cmd import raw_group
from octop_memory.adapters.cli.recall_cmd import recall_cmd
from octop_memory.adapters.cli.thread_cmd import thread_group

# dashboard is only available when the [dashboard] extra is installed
# (openclaw/hermes-specific). Its only purpose here is to probe for the
# optional extra, so importing it unconditionally at module scope (rather
# than at the bottom, after other setup) is safe: it never depends on
# anything defined later in this file.
dashboard_cmd: click.Command | None
try:
    from octop_memory.adapters.cli.dashboard import dashboard_cmd
except ImportError:
    dashboard_cmd = None


@click.group()
@click.version_option(version=__version__, prog_name="octop-memory")
@click.option(
    "--config",
    "config_path",
    envvar="OCTOP_MEMORY_CONFIG",
    default=None,
    type=click.Path(dir_okay=False),
    help="Path to config file (default: ~/.octop-memory/config.json).",
)
@click.option(
    "--backend",
    "-b",
    envvar="OCTOP_MEMORY_BACKEND",
    default=None,
    type=click.Choice(["sqlite", "postgres"], case_sensitive=False),
    help="Storage backend type.",
)
@click.option("--db", envvar="OCTOP_MEMORY_DB", default=None, help="SQLite database path.")
@click.option("--dsn", envvar="OCTOP_MEMORY_DSN", default=None, help="PostgreSQL connection string.")
@click.option("--namespace", "-n", envvar="OCTOP_MEMORY_NAMESPACE", default=None, help="Memory namespace.")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def main(
    ctx: click.Context,
    config_path: str | None,
    backend: str | None,
    db: str | None,
    dsn: str | None,
    namespace: str | None,
    output_json: bool,
) -> None:
    """octop-memory: CLI for the pluggable memory system."""
    ctx.ensure_object(dict)

    # Set config file path override if provided
    if config_path:
        set_config_path(Path(config_path))

    # Load config file as base
    file_config = load_config()

    # Resolve with priority: CLI flag > env var (handled by click) > config file > defaults
    ctx.obj["backend"] = backend or file_config.get("backend", "sqlite")
    ctx.obj["namespace"] = namespace or file_config.get("namespace", "default")
    ctx.obj["output_json"] = output_json

    # Resolve backend-specific options
    resolved_backend = ctx.obj["backend"]
    if resolved_backend == "sqlite":
        sqlite_config = file_config.get("sqlite", {})
        ctx.obj["db"] = db or sqlite_config.get("db_path", "~/.octop-memory/memory.db")
    else:
        ctx.obj["db"] = db or "~/.octop-memory/memory.db"

    if resolved_backend == "postgres":
        postgres_config = file_config.get("postgres", {})
        ctx.obj["dsn"] = dsn or postgres_config.get("dsn", "postgresql://localhost/octop_memory")
    else:
        ctx.obj["dsn"] = dsn or ""


main.add_command(config_group)
main.add_command(memory_group)
main.add_command(raw_group)
main.add_command(candidate_group)
main.add_command(atom_group)
main.add_command(entity_group)
main.add_command(journal_group)
main.add_command(page_group)
main.add_command(recall_cmd)
main.add_command(thread_group)
main.add_command(export_cmd)
main.add_command(import_cmd)
main.add_command(migrate_cmd)
main.add_command(backfill_cmd)
main.add_command(gc_group)
main.add_command(db_group)
main.add_command(consolidate_group)
main.add_command(openclaw_group)
main.add_command(episode_group)
main.add_command(digest_group)
main.add_command(portable_group)

if dashboard_cmd is not None:
    main.add_command(dashboard_cmd)
