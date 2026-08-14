"""Admin backup / restore API."""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from octop.api.common.content_disposition import content_disposition
from octop.api.deps import get_server, require_permission
from octop.config import load_config
from octop.infra.backup.auto import (
    AUTO_BACKUP_JOB_ID,
    BACKUP_LOCK,
    backup_config_from_payload,
    run_auto_backup,
    update_server_backup_config,
)
from octop.infra.backup.store import (
    delete_backup_file,
    list_backup_files,
    normalize_backup_filename,
    read_backup_file,
    write_backup_file,
)
from octop.infra.backup.system_archive import create_system_backup, restore_system_backup
from octop.infra.db.repos.audit import ACTOR_ADMIN
from octop.infra.errors import ErrorCode, OctopError

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


@router.get("/backup/auto", summary="Get automatic backup settings")
async def get_auto_backup_settings(
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return auto-backup config and whether the system job is currently scheduled."""
    return _auto_settings_payload(server)


@router.put("/backup/auto", summary="Update automatic backup settings")
async def put_auto_backup_settings(
    body: AutoBackupSettingsBody,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Persist auto-backup settings and reschedule the in-process system job."""
    backup = backup_config_from_payload(body.model_dump())
    update_server_backup_config(server, backup)
    return {"ok": True, **_auto_settings_payload(server)}


@router.post("/backup/auto/run", summary="Run automatic backup now")
async def run_auto_backup_now(
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create one automatic backup immediately (same path as the scheduled job)."""
    if BACKUP_LOCK.locked():
        raise OctopError(
            ErrorCode.BACKUP_IN_PROGRESS,
            "a backup is already in progress",
        )
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
    if BACKUP_LOCK.locked():
        raise OctopError(
            ErrorCode.BACKUP_IN_PROGRESS,
            "a backup is already in progress",
        )
    async with BACKUP_LOCK:
        data, filename = create_system_backup(
            paths=server.paths,
            agent_rows=_agent_rows(server),
            pool=server.services.db,
            db_config=server.services.config.database,
        )
        entry = write_backup_file(server.paths, filename, data)
    return {"ok": True, "item": entry.to_dict()}


@router.get(
    "/backup/files/{filename}",
    summary="Download a stored backup archive",
    response_class=StreamingResponse,
)
async def download_backup_file(
    filename: str,
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Stream a backup file from ``backups_dir``."""
    safe = normalize_backup_filename(filename)
    data = read_backup_file(server.paths, safe)
    return StreamingResponse(
        iter([data]),
        media_type="application/gzip",
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
    """
    assert server.services is not None
    safe = normalize_backup_filename(filename)
    raw = read_backup_file(server.paths, safe)
    result = restore_system_backup(
        raw,
        paths=server.paths,
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
    delete_backup_file(server.paths, safe)


@router.get(
    "/backup/export",
    summary="Download full system backup (ephemeral)",
    response_class=StreamingResponse,
)
async def export_backup(
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Create and stream a backup without persisting to ``backups_dir``."""
    assert server.services is not None
    data, filename = create_system_backup(
        paths=server.paths,
        agent_rows=_agent_rows(server),
        pool=server.services.db,
        db_config=server.services.config.database,
    )
    return StreamingResponse(
        iter([data]),
        media_type="application/gzip",
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
    entry = write_backup_file(server.paths, safe, raw)
    return {"ok": True, "item": entry.to_dict()}
