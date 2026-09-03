"""Automatic system backup scheduling (process-level CronManager job)."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from octop.config import BackupConfig, OctopConfig, load_config
from octop.infra.backup.store import (
    BackupFileInfo,
    is_auto_backup_filename,
    place_backup_file,
    prune_auto_backups,
)
from octop.infra.backup.system_archive import create_system_backup
from octop.infra.cron.trigger import build_trigger
from octop.infra.db.repos.audit import ACTOR_SYSTEM
from octop.infra.errors import ErrorCode, OctopError

if TYPE_CHECKING:
    from octop.config import DatabaseConfig
    from octop.infra.cron.manager import CronManager
    from octop.infra.db.pool import DatabasePool
    from octop.infra.server import OctopServer
    from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

AUTO_BACKUP_JOB_ID = "octop_auto_backup"
_AUTO_FILENAME_PREFIX = "octop-auto-backup-"
_MANUAL_FILENAME_PREFIX = "octop-backup-"

BackupOperation = Literal["create", "restore", "auto", "export"]

_lock = asyncio.Lock()
_active_operation: BackupOperation | None = None

# Shared with manual create so concurrent backups do not overlap.
BACKUP_LOCK = _lock


def get_backup_operation() -> BackupOperation | None:
    """Return the in-flight backup/restore kind, or ``None`` when idle."""
    if not _lock.locked():
        return None
    return _active_operation


def backup_status_payload() -> dict[str, Any]:
    op = get_backup_operation()
    return {"busy": op is not None, "operation": op}


@asynccontextmanager
async def hold_backup_lock(operation: BackupOperation) -> AsyncIterator[None]:
    """Acquire ``BACKUP_LOCK`` and publish *operation* for status polling."""
    global _active_operation
    async with _lock:
        _active_operation = operation
        try:
            yield
        finally:
            _active_operation = None


def raise_if_backup_busy() -> None:
    if _lock.locked():
        raise OctopError(
            ErrorCode.BACKUP_IN_PROGRESS,
            "a backup or restore is already in progress",
        )


def to_auto_backup_filename(suggested: str) -> str:
    """Map ``octop-backup-*.tar.gz`` → ``octop-auto-backup-*.tar.gz``."""
    name = Path(suggested).name
    if is_auto_backup_filename(name):
        return name
    if name.startswith(_MANUAL_FILENAME_PREFIX):
        return _AUTO_FILENAME_PREFIX + name.removeprefix(_MANUAL_FILENAME_PREFIX)
    raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"unexpected backup filename: {name!r}")


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def persist_backup_config(config_path: Path, backup: BackupConfig) -> OctopConfig:
    """Merge ``backup`` into ``config.json`` and return the reloaded config."""
    if config_path.exists():
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise OctopError(ErrorCode.INTERNAL_ERROR, "config.json must be a JSON object")
    else:
        raw = {}

    raw["backup"] = {
        "auto_enabled": backup.auto_enabled,
        "schedule": backup.schedule,
        "retention_count": backup.retention_count,
        "include_config": backup.include_config,
        "include_workspaces": backup.include_workspaces,
        "include_skill_packages": backup.include_skill_packages,
        "include_plugins": backup.include_plugins,
        "include_knowledge": backup.include_knowledge,
        "include_chats": backup.include_chats,
    }
    _atomic_write_json(config_path, raw)
    return load_config(config_path)


def backup_config_from_payload(payload: dict[str, Any]) -> BackupConfig:
    """Validate an API/CLI payload into ``BackupConfig``."""
    defaults = BackupConfig()
    schedule = str(payload.get("schedule", defaults.schedule)).strip() or defaults.schedule
    try:
        build_trigger(schedule)
    except OctopError as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid backup schedule: {schedule}") from exc
    try:
        retention = int(payload.get("retention_count", defaults.retention_count))
    except (TypeError, ValueError) as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "retention_count must be an integer") from exc
    if retention < 1:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "retention_count must be >= 1")
    return BackupConfig(
        auto_enabled=bool(payload.get("auto_enabled", defaults.auto_enabled)),
        schedule=schedule,
        retention_count=retention,
        include_config=bool(payload.get("include_config", defaults.include_config)),
        include_workspaces=bool(payload.get("include_workspaces", defaults.include_workspaces)),
        include_skill_packages=bool(
            payload.get("include_skill_packages", defaults.include_skill_packages)
        ),
        include_plugins=bool(payload.get("include_plugins", defaults.include_plugins)),
        include_knowledge=bool(payload.get("include_knowledge", defaults.include_knowledge)),
        include_chats=bool(payload.get("include_chats", defaults.include_chats)),
    )


def create_and_store_auto_backup(
    *,
    paths: PathLayout,
    agent_rows: list[Any],
    pool: DatabasePool,
    db_config: DatabaseConfig,
    retention_count: int,
    include_config: bool = True,
    include_workspaces: bool = True,
    include_skill_packages: bool = True,
    include_plugins: bool = True,
    include_knowledge: bool = True,
    include_chats: bool = False,
) -> tuple[BackupFileInfo, list[str]]:
    """Create a selected-content system backup with the auto prefix and prune."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "backup.tar.gz"
        suggested = create_system_backup(
            paths=paths,
            agent_rows=agent_rows,
            pool=pool,
            db_config=db_config,
            dest=tmp_path,
            include_config=include_config,
            include_workspaces=include_workspaces,
            include_skill_packages=include_skill_packages,
            include_plugins=include_plugins,
            include_knowledge=include_knowledge,
            include_chats=include_chats,
        )
        filename = to_auto_backup_filename(suggested)
        entry = place_backup_file(paths, filename, tmp_path)
    deleted = prune_auto_backups(paths, keep=retention_count)
    return entry, deleted


async def run_auto_backup(server: OctopServer) -> BackupFileInfo | None:
    """Run one automatic backup cycle. Returns ``None`` when skipped (busy/disabled)."""
    if _lock.locked():
        logger.info("auto backup skipped: another backup is already running")
        return None

    async with hold_backup_lock("auto"):
        config = load_config(server.paths.config)
        if server.services is None:
            logger.warning("auto backup skipped: server services not ready")
            return None

        retention = config.backup.retention_count
        try:
            if server.app_runtime is not None:
                agent_rows = cast(list[Any], server.app_runtime.agent_registry.list_rows())
            else:
                agent_rows = cast(list[Any], server.services.agent_repo.list_all())
            entry, deleted = await asyncio.to_thread(
                create_and_store_auto_backup,
                paths=server.paths,
                agent_rows=agent_rows,
                pool=server.services.db,
                db_config=server.services.config.database,
                retention_count=retention,
                include_config=config.backup.include_config,
                include_workspaces=config.backup.include_workspaces,
                include_skill_packages=config.backup.include_skill_packages,
                include_plugins=config.backup.include_plugins,
                include_knowledge=config.backup.include_knowledge,
                include_chats=config.backup.include_chats,
            )
        except Exception as exc:
            logger.exception("auto backup failed")
            try:
                server.services.audit_repo.write(
                    actor=ACTOR_SYSTEM,
                    action="backup.auto_failed",
                    target="",
                    payload=str(exc)[:500],
                )
            except Exception:
                logger.exception("failed to write backup.auto_failed audit")
            return None

        try:
            server.services.audit_repo.write(
                actor=ACTOR_SYSTEM,
                action="backup.auto_ok",
                target=entry.name,
                payload=json.dumps({"size": entry.size, "pruned": deleted}),
            )
        except Exception:
            logger.exception("failed to write backup.auto_ok audit")

        logger.info(
            "auto backup wrote %s (%d bytes); pruned %d",
            entry.name,
            entry.size,
            len(deleted),
        )
        return entry


def apply_auto_backup_schedule(cron_manager: CronManager, *, server: OctopServer) -> None:
    """Register or remove the auto-backup system job from current config."""
    cron_manager.unschedule_system_job(AUTO_BACKUP_JOB_ID)
    config = load_config(server.paths.config)
    if not config.backup.auto_enabled:
        logger.info("auto backup disabled; system job not scheduled")
        return

    schedule = config.backup.schedule
    try:
        build_trigger(schedule)
    except OctopError:
        logger.warning("auto backup schedule %r is invalid; not scheduling", schedule)
        return

    async def _run() -> None:
        await run_auto_backup(server)

    cron_manager.schedule_system_job(
        AUTO_BACKUP_JOB_ID,
        trigger=schedule,
        func=_run,
    )
    logger.info("auto backup job scheduled (%s)", schedule)


def install_auto_backup_job(cron_manager: CronManager, *, server: OctopServer) -> None:
    """Boot-time hook: schedule auto backup when enabled in config."""
    apply_auto_backup_schedule(cron_manager, server=server)


def update_server_backup_config(server: OctopServer, backup: BackupConfig) -> OctopConfig:
    """Persist backup settings, refresh in-memory config, and reschedule the job."""
    new_config = persist_backup_config(server.paths.config, backup)
    server.config = new_config
    if server.services is not None:
        server.services = replace(server.services, config=new_config)
    if server.app_runtime is not None:
        apply_auto_backup_schedule(server.app_runtime.cron_manager, server=server)
    return new_config
