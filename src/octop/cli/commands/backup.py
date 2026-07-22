"""`octop backup` — export and restore Octop data."""

from __future__ import annotations

from pathlib import Path

import click

from octop.config import load_config
from octop.infra.backup.system_archive import create_system_backup, restore_system_backup
from octop.infra.db.factory import open_database
from octop.infra.db.migrate import run_migrations
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout


def _paths(home: Path | None = None) -> PathLayout:
    return PathLayout(home) if home is not None else PathLayout.from_env()


@click.group()
def backup() -> None:
    """Backup and restore database + local agent workspaces."""


@backup.command("create")
@click.option(
    "-o", "--output", type=click.Path(path_type=Path), default=None, help="Output .tar.gz path."
)
@click.option(
    "--home", type=click.Path(path_type=Path), default=None, help="Octop home (default ~/.octop)."
)
def create(output: Path | None, home: Path | None) -> None:
    """Create a full backup archive."""
    paths = _paths(home)
    config = load_config(paths.config)
    db = open_database(config, paths)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=config)
    rows = services.agent_repo.list_all()
    data, suggested = create_system_backup(
        paths=paths,
        agent_rows=rows,
        pool=db,
        db_config=config.database,
    )
    db.close()

    if output is None:
        paths.ensure_backups_dir()
        dest = paths.backup_file(suggested)
    else:
        dest = output
    dest.write_bytes(data)
    click.echo(f"wrote {dest} ({len(data)} bytes)")


@backup.command("restore")
@click.argument("archive", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--home", type=click.Path(path_type=Path), default=None, help="Octop home (default ~/.octop)."
)
@click.option("--no-config", is_flag=True, default=False, help="Do not restore config.json / env.")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation.")
def restore(archive: Path, home: Path | None, no_config: bool, yes: bool) -> None:
    """Restore from a backup archive. Stop ``octop run`` first for a clean restore."""
    if not yes:
        click.confirm(
            "This overwrites the database and local workspaces. Continue?",
            abort=True,
        )
    paths = _paths(home)
    config = load_config(paths.config)
    db = open_database(config, paths)
    raw = archive.read_bytes()
    result = restore_system_backup(
        raw,
        paths=paths,
        pool=db,
        db_config=config.database,
        restore_config=not no_config,
    )
    db.close()
    click.echo(f"restored: {result}")
