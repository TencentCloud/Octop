"""Admin backup / restore API."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from octop.api.common.content_disposition import content_disposition
from octop.api.deps import get_server, require_permission
from octop.config import BackupConfig, DatabaseConfig, load_config
from octop.infra.backup.auto import (
    AUTO_BACKUP_JOB_ID,
    backup_config_from_payload,
    backup_status_payload,
    hold_backup_lock,
    raise_if_backup_busy,
    run_auto_backup,
    update_server_backup_config,
)
from octop.infra.backup.remote.index import MirrorIndex
from octop.infra.backup.remote.registry import get_provider
from octop.infra.backup.remote.resolve import (
    BACKUP_REMOTE_BACKEND_NAME,
    list_backup_destinations,
    provider_from_backend,
    raise_remote_mirror_failed,
    remote_summary,
    resolve_remote_engine,
    webdav_config_json,
)
from octop.infra.backup.store import (
    BackupFileInfo,
    backup_file_info,
    delete_backup_file,
    is_auto_backup_filename,
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
    include_config: bool = True
    include_workspaces: bool = True
    include_skill_packages: bool = True
    include_plugins: bool = True
    include_knowledge: bool = True
    include_chats: bool = False
    remote_enabled: bool = False
    remote_backend_id: int | None = None


class CreateBackupBody(BaseModel):
    include_config: bool = True
    include_workspaces: bool = True
    include_skill_packages: bool = True
    include_plugins: bool = True
    include_knowledge: bool = True
    include_chats: bool = False


class RemoteWebDavBody(BaseModel):
    """Draft or save payload for the Backup-managed WebDAV target."""

    url: str = Field(min_length=1)
    name: str = Field(default="", description="Display label for this WebDAV destination")
    username: str = ""
    password: str | None = None
    base_dir: str = ""
    verify_ssl: bool = True
    allow_insecure: bool = False


class RemotePullBody(BaseModel):
    filename: str = Field(min_length=1)


class RemoteMirrorBody(BaseModel):
    filename: str = Field(min_length=1)


def _agent_rows(server: Any) -> list[Any]:
    assert server.app_runtime is not None
    return cast(list[Any], server.app_runtime.agent_registry.list_rows())


def _get_backend(server: Any, backend_id: int) -> Any:
    assert server.services is not None
    return server.services.storage_backend_repo.get(backend_id)


def _assert_remote_backend_resolvable(server: Any, backup: BackupConfig) -> None:
    """Reject enabling remote without a backup-capable storage backend."""
    if not backup.remote_enabled:
        return
    assert server.services is not None
    row = server.services.storage_backend_repo.get(backup.remote_backend_id)
    if row is None:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"remote_backend_id {backup.remote_backend_id} not found",
        )
    # Validates kind + enabled; stubs raise BACKUP_REMOTE_UNSUPPORTED on use.
    provider_from_backend(row)


def _auto_settings_payload(server: Any) -> dict[str, Any]:
    config = load_config(server.paths.config)
    backup = config.backup
    scheduled = False
    runtime = getattr(server, "app_runtime", None)
    if runtime is not None and runtime.cron_manager is not None:
        scheduled = runtime.cron_manager.has_system_job(AUTO_BACKUP_JOB_ID)
    payload: dict[str, Any] = {
        "auto_enabled": backup.auto_enabled,
        "schedule": backup.schedule,
        "retention_count": backup.retention_count,
        "include_config": backup.include_config,
        "include_workspaces": backup.include_workspaces,
        "include_skill_packages": backup.include_skill_packages,
        "include_plugins": backup.include_plugins,
        "include_knowledge": backup.include_knowledge,
        "include_chats": backup.include_chats,
        "remote_enabled": backup.remote_enabled,
        "remote_backend_id": backup.remote_backend_id,
        "scheduled": scheduled,
    }
    if server.services is not None:
        payload["remote"] = remote_summary(
            paths=server.paths,
            backup=backup,
            get_backend=server.services.storage_backend_repo.get,
        )
        payload["destinations"] = list_backup_destinations(
            list_backends=server.services.storage_backend_repo.list_all,
        )
    else:
        payload["destinations"] = []
    return payload


async def _mirror_if_enabled(
    server: Any,
    *,
    entry: BackupFileInfo,
) -> dict[str, Any]:
    """Mirror ``entry`` when remote is enabled; fail closed unless ``remote_ok``.

    Manual create never auto-prunes the remote (only auto / Mirror-now for
    auto-prefixed archives prune after ``remote_ok``).
    """
    config = load_config(server.paths.config)
    assert server.services is not None
    engine = resolve_remote_engine(
        paths=server.paths,
        backup=config.backup,
        get_backend=server.services.storage_backend_repo.get,
    )
    if engine is None:
        return {"remote_status": None}
    local_path = server.paths.backups_dir / entry.name
    result = await engine.mirror(local_path, entry.name)
    if result.status != "remote_ok":
        raise_remote_mirror_failed(result.reason or result.status)
    return {
        "remote_status": result.status,
        "remote_reason": result.reason,
    }


def _raise_if_backup_busy() -> None:
    raise_if_backup_busy()


def _create_and_store_manual_backup(
    *,
    paths: PathLayout,
    agent_rows: list[Any],
    pool: DatabasePool,
    db_config: DatabaseConfig,
    options: CreateBackupBody,
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
            include_config=options.include_config,
            include_workspaces=options.include_workspaces,
            include_skill_packages=options.include_skill_packages,
            include_plugins=options.include_plugins,
            include_knowledge=options.include_knowledge,
            include_chats=options.include_chats,
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
        allow_legacy_history=False,
    )


def _create_ephemeral_backup(
    *,
    paths: PathLayout,
    agent_rows: list[Any],
    pool: DatabasePool,
    db_config: DatabaseConfig,
    options: CreateBackupBody,
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
            include_config=options.include_config,
            include_workspaces=options.include_workspaces,
            include_skill_packages=options.include_skill_packages,
            include_plugins=options.include_plugins,
            include_knowledge=options.include_knowledge,
            include_chats=options.include_chats,
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


def _remote_engine_or_none(server: Any) -> Any:
    """Return the remote engine when cloud destination is enabled."""
    config = load_config(server.paths.config)
    return resolve_remote_engine(
        paths=server.paths,
        backup=config.backup,
        get_backend=lambda backend_id: _get_backend(server, backend_id),
    )


@router.get("/backup/list", summary="List stored backup archives")
async def list_backups(
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """List backup archives for the active destination.

    When remote backup is enabled, the cloud catalog is authoritative (local
    disk is only a cache). Otherwise list ``~/.octop/backups/``.
    """
    engine = _remote_engine_or_none(server)
    if engine is not None:
        items = await engine.list_catalog()
        return {
            "dir": str(server.paths.backups_dir),
            "source": "remote",
            "items": items,
        }
    files = await asyncio.to_thread(list_backup_files, server.paths)
    index = MirrorIndex.for_paths(server.paths)
    local_items: list[dict[str, Any]] = []
    for entry in files:
        payload: dict[str, Any] = dict(entry.to_dict())
        mirror = index.get(entry.name)
        if mirror is not None:
            payload["remote_status"] = mirror.status
            payload["remote_checked_at"] = mirror.checked_at
            if mirror.detail:
                payload["remote_detail"] = mirror.detail
        else:
            payload["remote_status"] = None
        local_items.append(payload)
    return {
        "dir": str(server.paths.backups_dir),
        "source": "local",
        "items": local_items,
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
    _assert_remote_backend_resolvable(server, backup)
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
    item = dict(entry.to_dict())
    mirror = MirrorIndex.for_paths(server.paths).get(entry.name)
    if mirror is not None:
        item["remote_status"] = mirror.status
    return {"ok": True, "item": item}


@router.post("/backup/create", summary="Create backup and save to backups dir")
async def create_backup(
    body: CreateBackupBody | None = None,
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create a selected-content backup and persist it under ``backups_dir``.

    When remote mirroring is enabled, overall success requires ``remote_ok``.
    """
    assert server.services is not None
    options = body or CreateBackupBody()
    _raise_if_backup_busy()
    async with hold_backup_lock("create"):
        entry = await asyncio.to_thread(
            _create_and_store_manual_backup,
            paths=server.paths,
            agent_rows=_agent_rows(server),
            pool=server.services.db,
            db_config=server.services.config.database,
            options=options,
        )
        remote_meta = await _mirror_if_enabled(server, entry=entry)
    item = dict(entry.to_dict())
    if remote_meta.get("remote_status") is not None:
        item["remote_status"] = remote_meta["remote_status"]
    return {"ok": True, "item": item, **{k: v for k, v in remote_meta.items() if v is not None}}


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
    """Stream a backup file from ``backups_dir`` without loading it into memory.

    When the cloud destination is enabled and the local cache is missing, pull
    the archive first.
    """
    safe = normalize_backup_filename(filename)
    engine = _remote_engine_or_none(server)
    if engine is not None:
        path = await engine.ensure_local(safe)
    else:
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
    engine = _remote_engine_or_none(server)
    async with hold_backup_lock("restore"):
        if engine is not None:
            await engine.ensure_local(safe)
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
    """Remove a backup from the active destination (and local cache if present)."""
    safe = normalize_backup_filename(filename)
    engine = _remote_engine_or_none(server)
    if engine is not None:
        await engine.delete_remote(safe)
        local = server.paths.backup_file(safe)
        if local.is_file():
            local.unlink()
        return
    await asyncio.to_thread(delete_backup_file, server.paths, safe)


@router.get(
    "/backup/export",
    summary="Download selected system backup (ephemeral)",
    response_class=FileResponse,
)
async def export_backup(
    background_tasks: BackgroundTasks,
    include_config: bool = Query(default=True),
    include_workspaces: bool = Query(default=True),
    include_skill_packages: bool = Query(default=True),
    include_plugins: bool = Query(default=True),
    include_knowledge: bool = Query(default=True),
    include_chats: bool = Query(default=False),
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
            options=CreateBackupBody(
                include_config=include_config,
                include_workspaces=include_workspaces,
                include_skill_packages=include_skill_packages,
                include_plugins=include_plugins,
                include_knowledge=include_knowledge,
                include_chats=include_chats,
            ),
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


@router.put("/backup/remote", summary="Save Backup-managed WebDAV remote target")
async def put_remote_backup_target(
    body: RemoteWebDavBody,
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create or update the dedicated WebDAV ``storage_backends`` row and link it.

    Saving credentials does **not** enable remote mirroring; set
    ``remote_enabled`` via ``PUT /backup/auto`` separately.
    """
    assert server.services is not None
    # Validate draft settings before writing secrets.
    get_provider(
        "webdav",
        url=body.url,
        username=body.username,
        password=body.password or "",
        base_dir=body.base_dir,
        verify_ssl=body.verify_ssl,
        allow_insecure=body.allow_insecure,
    )
    repo = server.services.storage_backend_repo
    existing = repo.get_by_name(BACKUP_REMOTE_BACKEND_NAME)
    label = body.name.strip()
    config_json = webdav_config_json(
        base_dir=body.base_dir,
        verify_ssl=body.verify_ssl,
        allow_insecure=body.allow_insecure,
        label=label,
    )
    username = body.username.strip()
    endpoint = body.url.strip()
    note = label or "Managed by Backup → Remote"
    if existing is None:
        backend_id = repo.create(
            name=BACKUP_REMOTE_BACKEND_NAME,
            kind="webdav",
            endpoint=endpoint,
            access_key=username or None,
            secret_key=body.password if body.password is not None else None,
            config_json=config_json,
            note=note,
        )
    else:
        backend_id = existing.id
        same_endpoint = (existing.endpoint or "").rstrip("/") == endpoint.rstrip("/")
        # Empty password means "keep stored secret" only for the same endpoint.
        # Changing the URL without a new password must not re-bind a stored secret.
        if body.password is not None:
            secret = body.password
        elif not same_endpoint and (existing.secret_key or ""):
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                "password is required when changing the WebDAV URL",
            )
        elif not same_endpoint or not username and (existing.access_key or ""):
            secret = ""
        else:
            secret = existing.secret_key or ""
        repo.update(
            backend_id,
            kind="webdav",
            endpoint=endpoint,
            access_key=username,
            secret_key=secret,
            config_json=config_json,
            enabled=True,
            note=note,
        )
    config = load_config(server.paths.config)
    backup = replace(config.backup, remote_backend_id=backend_id)
    update_server_backup_config(server, backup)
    return {"ok": True, **_auto_settings_payload(server)}


@router.post("/backup/remote/test", summary="Test remote backup connectivity")
async def test_remote_backup(
    body: RemoteWebDavBody | None = None,
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Probe draft WebDAV settings or the currently linked remote backend."""
    assert server.services is not None
    if body is not None:
        config = load_config(server.paths.config)
        stored = None
        if config.backup.remote_backend_id is not None:
            stored = _get_backend(server, config.backup.remote_backend_id)
        password = body.password
        # ``None`` = keep stored secret for the same endpoint; ``""`` = probe
        # with an empty password. Never send stored creds to a new URL.
        if password is None:
            if stored is not None and (stored.endpoint or "").rstrip(
                "/"
            ) == body.url.strip().rstrip("/"):
                password = stored.secret_key or ""
            else:
                password = ""
        provider = get_provider(
            "webdav",
            url=body.url,
            username=body.username,
            password=password,
            base_dir=body.base_dir,
            verify_ssl=body.verify_ssl,
            allow_insecure=body.allow_insecure,
        )
    else:
        config = load_config(server.paths.config)
        backend_id = config.backup.remote_backend_id
        if backend_id is None:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                "no remote backup backend configured; pass draft WebDAV settings",
            )
        row = _get_backend(server, backend_id)
        if row is None:
            raise OctopError(
                ErrorCode.BACKUP_REMOTE_FAILED,
                f"remote backup backend id {backend_id} not found",
                details={"detail": f"backend {backend_id} not found"},
            )
        provider = provider_from_backend(row)
    await provider.test()
    return {"ok": True}


@router.get("/backup/remote/list", summary="List remote backup archives")
async def list_remote_backups(
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """List archives on the configured remote target (requires a linked backend)."""
    assert server.services is not None
    config = load_config(server.paths.config)
    backend_id = config.backup.remote_backend_id
    if backend_id is None:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "no remote backup backend configured")
    row = _get_backend(server, backend_id)
    if row is None:
        raise OctopError(
            ErrorCode.BACKUP_REMOTE_FAILED,
            f"remote backup backend id {backend_id} not found",
            details={"detail": f"backend {backend_id} not found"},
        )
    engine = resolve_remote_engine(
        paths=server.paths,
        # list/pull do not require remote_enabled; only a resolvable backend.
        backup=BackupConfig(
            remote_enabled=True,
            remote_backend_id=backend_id,
        ),
        get_backend=server.services.storage_backend_repo.get,
    )
    assert engine is not None
    objects = await engine.list_remote()
    index = MirrorIndex.for_paths(server.paths)
    items: list[dict[str, Any]] = []
    for obj in objects:
        payload: dict[str, Any] = {
            "name": obj.name,
            "size": obj.size,
            "modified_at": obj.modified_at,
        }
        mirror = index.get(obj.name)
        if mirror is not None:
            payload["remote_status"] = mirror.status
            payload["remote_checked_at"] = mirror.checked_at
        items.append(payload)
    return {"items": items}


@router.post("/backup/remote/pull", summary="Pull a remote archive into backups dir")
async def pull_remote_backup(
    body: RemotePullBody,
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Download one remote archive into ``backups_dir`` (no overwrite)."""
    assert server.services is not None
    _raise_if_backup_busy()
    safe = normalize_backup_filename(body.filename)
    config = load_config(server.paths.config)
    backend_id = config.backup.remote_backend_id
    if backend_id is None:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "no remote backup backend configured")
    async with hold_backup_lock("create"):
        engine = resolve_remote_engine(
            paths=server.paths,
            backup=BackupConfig(remote_enabled=True, remote_backend_id=backend_id),
            get_backend=server.services.storage_backend_repo.get,
        )
        assert engine is not None
        dest = await engine.pull(safe)
    entry = await asyncio.to_thread(backup_file_info, dest)
    return {"ok": True, "item": entry.to_dict()}


@router.post("/backup/remote/mirror", summary="Mirror a local archive to remote now")
async def mirror_remote_backup(
    body: RemoteMirrorBody,
    _: Any = Depends(require_permission("backup")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Re-upload an existing local archive; overall success requires ``remote_ok``."""
    assert server.services is not None
    _raise_if_backup_busy()
    safe = normalize_backup_filename(body.filename)
    path = await asyncio.to_thread(resolve_backup_path, server.paths, safe)
    config = load_config(server.paths.config)
    if not config.backup.remote_enabled:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "remote backup is not enabled")
    async with hold_backup_lock("create"):
        engine = resolve_remote_engine(
            paths=server.paths,
            backup=config.backup,
            get_backend=server.services.storage_backend_repo.get,
        )
        assert engine is not None
        result = await engine.mirror(path, safe)
        remote_pruned: list[str] = []
        if result.status == "remote_ok":
            if is_auto_backup_filename(safe):
                remote_pruned = await engine.prune_auto(
                    keep=config.backup.retention_count,
                    newest_status=result.status,
                )
        else:
            raise_remote_mirror_failed(result.reason or result.status)
    return {
        "ok": True,
        "name": safe,
        "remote_status": result.status,
        "remote_reason": result.reason,
        "remote_pruned": remote_pruned,
    }
