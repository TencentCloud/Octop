"""Automatic system backup scheduling (process-level CronManager job)."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from octop.config import BackupConfig, OctopConfig, load_config
from octop.infra.backup.store import (
    BackupFileInfo,
    is_auto_backup_filename,
    prune_auto_backups,
    write_backup_file,
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

_lock = asyncio.Lock()

# Shared with manual create so concurrent backups do not overlap.
BACKUP_LOCK = _lock


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
    )


def create_and_store_auto_backup(
    *,
    paths: PathLayout,
    agent_rows: list[Any],
    pool: DatabasePool,
    db_config: DatabaseConfig,
    retention_count: int,
) -> tuple[BackupFileInfo, list[str]]:
    """Create a full system backup with the auto filename prefix and prune."""
    data, suggested = create_system_backup(
        paths=paths,
        agent_rows=agent_rows,
        pool=pool,
        db_config=db_config,
    )
    filename = to_auto_backup_filename(suggested)
    entry = write_backup_file(paths, filename, data)
    deleted = prune_auto_backups(paths, keep=retention_count)
    return entry, deleted


async def run_auto_backup(server: OctopServer) -> BackupFileInfo | None:
    """Run one automatic backup cycle. Returns ``None`` when skipped (busy/disabled)."""
    if _lock.locked():
        logger.info("auto backup skipped: another backup is already running")
        return None

    async with _lock:
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
