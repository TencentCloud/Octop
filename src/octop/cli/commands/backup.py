"""`octop backup` — export and restore Octop data."""

from __future__ import annotations

import errno
import os
import shutil
import tempfile
from pathlib import Path

import click

from octop.config import load_config
from octop.infra.backup.auto import create_and_store_auto_backup
from octop.infra.backup.store import place_backup_file
from octop.infra.backup.system_archive import create_system_backup, restore_system_backup
from octop.infra.db.factory import open_database
from octop.infra.db.migrate import run_migrations
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout


def _paths(home: Path | None = None) -> PathLayout:
    return PathLayout(home) if home is not None else PathLayout.from_env()


def _atomic_move_to(src: Path, dest: Path, _replace=None) -> None:
    """Move ``src`` onto ``dest`` even when they live on different filesystems.

    Prefers an atomic ``Path.replace`` (works only on the same filesystem). When
    ``--output`` points at a different mount than Python's temporary directory,
    ``replace`` fails with ``EXDEV`` (cross-device link) and the freshly built
    archive would be lost to temporary-directory cleanup. In that case fall back
    to copying into a staging file on the *destination* filesystem and then
    atomically swapping it into place, so a pre-existing destination is never
    left half-written if the copy fails.
    """
    replace = _replace or Path.replace
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        replace(src, dest)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
    _cross_device_copy(src, dest)


def _cross_device_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, stage = tempfile.mkstemp(dir=str(dest.parent), prefix=".octop-backup-", suffix=".tmp")
    os.close(fd)
    stage_path = Path(stage)
    try:
        shutil.copy2(src, stage_path)
        os.replace(stage_path, dest)
    finally:
        # The staging file is consumed by the atomic swap above; clean up only a
        # leftover from a failed swap so it does not linger in the destination dir.
        try:
            stage_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


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
@click.option("--no-config", is_flag=True, help="Do not include config.json / env.")
@click.option("--no-workspaces", is_flag=True, help="Do not include agent workspaces.")
@click.option("--no-skill-packages", is_flag=True, help="Do not include global skill packages.")
@click.option("--no-plugins", is_flag=True, help="Do not include installed plugins.")
@click.option("--no-knowledge", is_flag=True, help="Do not include knowledge base files.")
@click.option("--include-chats", is_flag=True, help="Include chat history (omitted by default).")
def create(
    output: Path | None,
    home: Path | None,
    no_config: bool,
    no_workspaces: bool,
    no_skill_packages: bool,
    no_plugins: bool,
    no_knowledge: bool,
    include_chats: bool,
) -> None:
    """Create a selected-content backup archive."""
    paths = _paths(home)
    config = load_config(paths.config)
    db = open_database(config, paths)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=config)
    rows = services.agent_repo.list_all()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "backup.tar.gz"
            suggested = create_system_backup(
                paths=paths,
                agent_rows=rows,
                pool=db,
                db_config=config.database,
                dest=tmp_path,
                include_config=not no_config,
                include_workspaces=not no_workspaces,
                include_skill_packages=not no_skill_packages,
                include_plugins=not no_plugins,
                include_knowledge=not no_knowledge,
                include_chats=include_chats,
            )
            if output is None:
                entry = place_backup_file(paths, suggested, tmp_path)
                dest = paths.backup_file(entry.name)
                size = entry.size
            else:
                dest = output
                dest.parent.mkdir(parents=True, exist_ok=True)
                _atomic_move_to(tmp_path, dest)
                size = dest.stat().st_size
    finally:
        db.close()

    click.echo(f"wrote {dest} ({size} bytes)")


@backup.group("auto")
def auto() -> None:
    """Automatic backup status and one-shot run (schedule requires ``octop run``)."""


@auto.command("status")
@click.option(
    "--home", type=click.Path(path_type=Path), default=None, help="Octop home (default ~/.octop)."
)
def auto_status(home: Path | None) -> None:
    """Print automatic backup settings from config.json."""
    paths = _paths(home)
    config = load_config(paths.config)
    backup_cfg = config.backup
    click.echo(f"auto_enabled: {backup_cfg.auto_enabled}")
    click.echo(f"schedule: {backup_cfg.schedule}")
    click.echo(f"retention_count: {backup_cfg.retention_count}")
    click.echo(f"include_config: {backup_cfg.include_config}")
    click.echo(f"include_workspaces: {backup_cfg.include_workspaces}")
    click.echo(f"include_skill_packages: {backup_cfg.include_skill_packages}")
    click.echo(f"include_plugins: {backup_cfg.include_plugins}")
    click.echo(f"include_knowledge: {backup_cfg.include_knowledge}")
    click.echo(f"include_chats: {backup_cfg.include_chats}")
    click.echo("note: the scheduler only runs inside an active `octop run` process")


@auto.command("run")
@click.option(
    "--home", type=click.Path(path_type=Path), default=None, help="Octop home (default ~/.octop)."
)
def auto_run(home: Path | None) -> None:
    """Create one automatic backup now and apply retention pruning."""
    paths = _paths(home)
    config = load_config(paths.config)
    db = open_database(config, paths)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=config)
    rows = services.agent_repo.list_all()
    try:
        entry, deleted = create_and_store_auto_backup(
            paths=paths,
            agent_rows=rows,
            pool=db,
            db_config=config.database,
            retention_count=config.backup.retention_count,
            include_config=config.backup.include_config,
            include_workspaces=config.backup.include_workspaces,
            include_skill_packages=config.backup.include_skill_packages,
            include_plugins=config.backup.include_plugins,
            include_knowledge=config.backup.include_knowledge,
            include_chats=config.backup.include_chats,
        )
    finally:
        db.close()
    click.echo(f"wrote {paths.backup_file(entry.name)} ({entry.size} bytes)")
    if deleted:
        click.echo(f"pruned: {', '.join(deleted)}")


@backup.command("restore")
@click.argument("archive", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--home", type=click.Path(path_type=Path), default=None, help="Octop home (default ~/.octop)."
)
@click.option("--no-config", is_flag=True, default=False, help="Do not restore config.json / env.")
@click.option(
    "--owner-user-id",
    type=int,
    default=None,
    help="For LightClaw migration archives: Octop user id that receives imported ownership "
    "(default: first admin among current users).",
)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation.")
def restore(
    archive: Path,
    home: Path | None,
    no_config: bool,
    owner_user_id: int | None,
    yes: bool,
) -> None:
    """Restore from a backup archive. Stop ``octop run`` first for a clean restore."""
    if not yes:
        click.confirm(
            "This overwrites the database and local workspaces. Continue?",
            abort=True,
        )
    paths = _paths(home)
    config = load_config(paths.config)
    db = open_database(config, paths)
    result = restore_system_backup(
        archive,
        paths=paths,
        pool=db,
        db_config=config.database,
        restore_config=not no_config,
        owner_user_id=owner_user_id,
    )
    db.close()
    click.echo(f"restored: {result}")
