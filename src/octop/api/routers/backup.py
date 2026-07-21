"""Admin backup / restore API."""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from octop.api.common.content_disposition import content_disposition
from octop.api.deps import current_admin, get_server
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


def _resolve_db_path(server: Any) -> Any:
    assert server.services is not None
    config = server.services.config
    if config.database_in_file or config.database.is_sqlite:
        return config.database.resolve_sqlite_path(server.paths.root)
    return server.paths.db


def _agent_rows(server: Any) -> list[Any]:
    assert server.app_runtime is not None
    return cast(list[Any], server.app_runtime.agent_registry.list_rows())


async def _rehydrate_runtime_after_restore(server: Any) -> None:
    """Sync restored providers into harness and reload agents (no process restart)."""
    runtime = getattr(server, "app_runtime", None)
    if runtime is None:
        return
    registry = getattr(runtime, "agent_registry", None)
    if registry is None:
        return
    try:
        await registry.on_provider_changed()
    except Exception:
        logger.exception("post-restore provider/agent rehydrate failed")


@router.get("/backup/list", summary="List stored backup archives")
async def list_backups(
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """List ``.tar.gz`` files in ``~/.octop/backups/``."""
    files = list_backup_files(server.paths)
    return {
        "dir": str(server.paths.backups_dir),
        "items": [f.to_dict() for f in files],
    }


@router.post("/backup/create", summary="Create backup and save to backups dir")
async def create_backup(
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create a full backup archive and persist it under ``backups_dir``."""
    db_path = _resolve_db_path(server)
    data, filename = create_system_backup(
        paths=server.paths,
        db_path=db_path,
        agent_rows=_agent_rows(server),
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
    _: Any = Depends(current_admin),
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
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Restore database and workspaces from a file in ``backups_dir``.

    After the archive is applied, providers are synced into the harness and agents
    are reloaded in-process so experts can run without a full service restart.
    Restored ``config.json`` / ``env`` still require a process restart to take effect.
    """
    assert server.services is not None
    safe = normalize_backup_filename(filename)
    raw = read_backup_file(server.paths, safe)
    db_path = _resolve_db_path(server)
    result = restore_system_backup(
        raw,
        paths=server.paths,
        db_path=db_path,
        pool=server.services.db,
        restore_config=restore_config,
    )
    await _rehydrate_runtime_after_restore(server)
    server.services.audit_repo.write(
        actor=ACTOR_ADMIN,
        action="backup.restore",
        target=safe,
        payload=str(result),
    )
    return {"ok": True, "name": safe, **result}


@router.delete("/backup/files/{filename}", summary="Delete a stored backup", status_code=204)
async def remove_backup_file(
    filename: str,
    _: Any = Depends(current_admin),
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
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Create and stream a backup without persisting to ``backups_dir``."""
    db_path = _resolve_db_path(server)
    data, filename = create_system_backup(
        paths=server.paths,
        db_path=db_path,
        agent_rows=_agent_rows(server),
    )
    return StreamingResponse(
        iter([data]),
        media_type="application/gzip",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.post("/backup/import", summary="Upload backup archive to backups dir")
async def import_backup(
    file: UploadFile = File(...),  # noqa: B008
    _: Any = Depends(current_admin),
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
