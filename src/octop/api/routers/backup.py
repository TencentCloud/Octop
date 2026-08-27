"""Admin backup / restore API."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from octop.api.common.content_disposition import content_disposition
from octop.api.deps import get_server, require_permission
from octop.config import DatabaseConfig, load_config
from octop.infra.backup.auto import (
    AUTO_BACKUP_JOB_ID,
    backup_config_from_payload,
    backup_status_payload,
    hold_backup_lock,
    raise_if_backup_busy,
    run_auto_backup,
    update_server_backup_config,
)
from octop.infra.backup.store import (
    BackupFileInfo,
    delete_backup_file,
    list_backup_files,
    normalize_backup_filename,
    place_backup_file,
    resolve_backup_path,
    write_backup_file,
)
from octop.infra.backup.system_archive import create_system_backup, restore_system_backup
from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos.audit import ACTOR_ADMIN
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_IMPORT_BYTES = 512 * 1024 * 1024


class AutoBackupSettingsBody(BaseModel):
    auto_enabled: bool = False
    schedule: str = Field(default="cron:0 4 * * *", min_length=1)
    retention_count: int = Field(default=7, ge=1, le=365)


def _agent_rows(server: Any) -> list[Any]:
    assert server.app_runtime is not None
    return cast(list[Any], server.app_runtime.agent_registry.list_rows())


def _auto_settings_payload(server: Any) -> dict[str, Any]:
    config = load_config(server.paths.config)
    backup = config.backup
    scheduled = False
    runtime = getattr(server, "app_runtime", None)
    if runtime is not None and runtime.cron_manager is not None:
        scheduled = runtime.cron_manager.has_system_job(AUTO_BACKUP_JOB_ID)
    return {
        "auto_enabled": backup.auto_enabled,
        "schedule": backup.schedule,
        "retention_count": backup.retention_count,
        "scheduled": scheduled,
    }


def _raise_if_backup_busy() -> None:
    raise_if_backup_busy()


def _create_and_store_manual_backup(
    *,
    paths: PathLayout,
    agent_rows: list[Any],
    pool: DatabasePool,
    db_config: DatabaseConfig,
) -> BackupFileInfo:
    """Sync create + place for ``asyncio.to_thread`` (keeps the event loop free)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "backup.tar.gz"
        filename = create_system_backup(
            paths=paths,
            agent_rows=agent_rows,
            pool=pool,
            db_config=db_config,
            dest=tmp_path,
        )
        return place_backup_file(paths, filename, tmp_path)


def _restore_stored_backup(
    *,
    paths: PathLayout,
    filename: str,
    pool: DatabasePool,
    db_config: DatabaseConfig,
    restore_config: bool,
    owner_user_id: int,
) -> dict[str, Any]:
    """Sync path-based restore for ``asyncio.to_thread``."""
    archive = resolve_backup_path(paths, filename)
    return restore_system_backup(
        archive,
        paths=paths,
        pool=pool,
        db_config=db_config,
        restore_config=restore_config,
        owner_user_id=owner_user_id,
    )


def _create_ephemeral_backup(
    *,
    paths: PathLayout,
    agent_rows: list[Any],
    pool: DatabasePool,
    db_config: DatabaseConfig,
) -> tuple[Path, str]:
    """Write a backup to a temp file; caller must delete after the response is sent."""
    fd, name = tempfile.mkstemp(prefix="octop-export-", suffix=".tar.gz")
    os.close(fd)
    tmp_path = Path(name)
    try:
        filename = create_system_backup(
            paths=paths,
            agent_rows=agent_rows,
            pool=pool,
            db_config=db_config,
            dest=tmp_path,
        )
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path, filename


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("failed to remove ephemeral backup %s", path, exc_info=True)


async def _rehydrate_runtime_after_restore(server: Any) -> None:
    """Sync restored providers/agents, IM channels, and cron (no process restart)."""
    runtime = getattr(server, "app_runtime", None)
    if runtime is None:
        return
    registry = getattr(runtime, "agent_registry", None)
    if registry is not None:
        try:
            await registry.on_provider_changed()
        except Exception:
            logger.exception("post-restore provider/agent rehydrate failed")
    gateway = getattr(runtime, "gateway", None)
    if gateway is not None:
        try:
            await gateway.reload_channels_from_db()
        except Exception:
            logger.exception("post-restore channel rehydrate failed")
    cron_manager = getattr(runtime, "cron_manager", None)
    if cron_manager is not None:
        try:
            await cron_manager.reload_from_db()
        except Exception:
            logger.exception("post-restore cron rehydrate failed")


@router.get("/backup/list", summary="List stored backup archives")
async def list_backups(
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """List ``.tar.gz`` files in ``~/.octop/backups/``."""
    files = list_backup_files(server.paths)
    return {
        "dir": str(server.paths.backups_dir),
        "items": [f.to_dict() for f in files],
    }


@router.get("/backup/status", summary="Whether a backup or restore is in progress")
async def get_backup_status(
    _: Any = Depends(require_permission("backup")),
) -> dict[str, Any]:
    """Return lock state for dashboard busy UI across navigation / refresh."""
    return backup_status_payload()


@router.get("/backup/auto", summary="Get automatic backup settings")
async def get_auto_backup_settings(
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return auto-backup config and whether the system job is currently scheduled."""
    return _auto_settings_payload(server)


@router.put("/backup/auto", summary="Update automatic backup settings")
async def put_auto_backup_settings(
    body: AutoBackupSettingsBody,
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Persist auto-backup settings and reschedule the in-process system job."""
    backup = backup_config_from_payload(body.model_dump())
    update_server_backup_config(server, backup)
    return {"ok": True, **_auto_settings_payload(server)}


@router.post("/backup/auto/run", summary="Run automatic backup now")
async def run_auto_backup_now(
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create one automatic backup immediately (same path as the scheduled job)."""
    _raise_if_backup_busy()
    entry = await run_auto_backup(server)
    if entry is None:
        raise OctopError(
            ErrorCode.BACKUP_IN_PROGRESS,
            "auto backup skipped (busy or runtime not ready)",
        )
    return {"ok": True, "item": entry.to_dict()}


@router.post("/backup/create", summary="Create backup and save to backups dir")
async def create_backup(
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create a full backup archive and persist it under ``backups_dir``."""
    assert server.services is not None
    _raise_if_backup_busy()
    async with hold_backup_lock("create"):
        entry = await asyncio.to_thread(
            _create_and_store_manual_backup,
            paths=server.paths,
            agent_rows=_agent_rows(server),
            pool=server.services.db,
            db_config=server.services.config.database,
        )
    return {"ok": True, "item": entry.to_dict()}


@router.get(
    "/backup/files/{filename}",
    summary="Download a stored backup archive",
    response_class=FileResponse,
)
async def download_backup_file(
    filename: str,
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> FileResponse:
    """Stream a backup file from ``backups_dir`` without loading it into memory."""
    safe = normalize_backup_filename(filename)
    path = await asyncio.to_thread(resolve_backup_path, server.paths, safe)
    return FileResponse(
        path,
        media_type="application/gzip",
        filename=safe,
        headers={"Content-Disposition": content_disposition(safe)},
    )


@router.post("/backup/files/{filename}/restore", summary="Restore from stored backup")
async def restore_backup_file(
    filename: str,
    restore_config: bool = Query(default=True),
    user: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Restore database and workspaces from a file in ``backups_dir``.

    After the archive is applied, providers/agents, IM channels, and cron jobs
    are reloaded in-process so experts, messaging, and schedules can run without
    a full service restart.
    Restored ``config.json`` / ``env`` still require a process restart to take effect.

    LightClaw migration archives reassign imported ownership to the restoring admin.

    Heavy disk/DB work runs in a worker thread so the asyncio event loop stays
    responsive; concurrent create/restore/auto backup is rejected via
    ``BACKUP_LOCK``. SQLite restore still holds the shared DB lock for the
    merge window, so DB-backed APIs may briefly queue during that phase.
    """
    assert server.services is not None
    _raise_if_backup_busy()
    safe = normalize_backup_filename(filename)
    async with hold_backup_lock("restore"):
        result = await asyncio.to_thread(
            _restore_stored_backup,
            paths=server.paths,
            filename=safe,
            pool=server.services.db,
            db_config=server.services.config.database,
            restore_config=restore_config,
            owner_user_id=int(user.id),
        )
        await _rehydrate_runtime_after_restore(server)
    server.services.audit_repo.write(
        actor=getattr(user, "username", None) or ACTOR_ADMIN,
        action="backup.restore",
        target=safe,
        payload=str(result),
    )
    return {"ok": True, "name": safe, **result}


@router.delete("/backup/files/{filename}", summary="Delete a stored backup", status_code=204)
async def remove_backup_file(
    filename: str,
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> None:
    """Remove a backup archive from ``backups_dir``."""
    safe = normalize_backup_filename(filename)
    await asyncio.to_thread(delete_backup_file, server.paths, safe)


@router.get(
    "/backup/export",
    summary="Download full system backup (ephemeral)",
    response_class=FileResponse,
)
async def export_backup(
    background_tasks: BackgroundTasks,
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> FileResponse:
    """Create and stream a backup without persisting to ``backups_dir``."""
    assert server.services is not None
    _raise_if_backup_busy()
    async with hold_backup_lock("export"):
        tmp_path, filename = await asyncio.to_thread(
            _create_ephemeral_backup,
            paths=server.paths,
            agent_rows=_agent_rows(server),
            pool=server.services.db,
            db_config=server.services.config.database,
        )
    background_tasks.add_task(_unlink_quiet, tmp_path)
    return FileResponse(
        tmp_path,
        media_type="application/gzip",
        filename=filename,
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.post("/backup/import", summary="Upload backup archive to backups dir")
async def import_backup(
    file: UploadFile = File(...),  # noqa: B008
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Save an uploaded ``.tar.gz`` into ``backups_dir`` (does not restore)."""
    raw = await file.read()
    if len(raw) > _MAX_IMPORT_BYTES:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "backup archive too large (max 512MB)")
    if not raw:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "empty backup archive")

    name = file.filename or "uploaded-backup.tar.gz"
    safe = normalize_backup_filename(name)
    entry = await asyncio.to_thread(write_backup_file, server.paths, safe, raw)
    return {"ok": True, "item": entry.to_dict()}
