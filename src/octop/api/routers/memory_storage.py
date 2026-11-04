"""Owner-authorized storage inspection and host-coordinated expert maintenance."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from octop.api.common.agent import require_agent_owner_row
from octop.api.deps import current_user, get_server, require_permission
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter(
    prefix="/agents/{agent_id}/memory/storage",
    dependencies=[Depends(require_permission("memory"))],
)


class StorageTableCheck(BaseModel):
    table: str
    exists: bool
    live_tuples: int | None = None
    dead_tuples: int | None = None
    last_vacuum: str | None = None
    last_autovacuum: str | None = None


class NamespaceTableCheck(BaseModel):
    table: str
    rows: int
    row_bytes: int


class CleanupPreview(BaseModel):
    candidates: int
    journal: int
    total: int
    limit_per_table: int
    candidate_days: int
    journal_days: int


class SqliteCountCheck(BaseModel):
    table: str = Field(description="Logical data category, excluding full-text index duplicates.")
    rows: int | None = Field(description="Exact snapshot count; null when missing or timed out.")
    status: Literal["ok", "missing", "timed_out"]
    elapsed_ms: float = Field(description="Server-side count query duration in milliseconds.")


class StorageInspection(BaseModel):
    backend: str
    scope: Literal["agent", "shared_database"]
    maintenance_supported: bool
    blocked_reason: (
        Literal["postgres", "shared_sqlite", "shared_namespace", "incompatible"] | None
    ) = None
    checked_at: float
    elapsed_ms: float | None = Field(
        default=None, description="Server inspection time, not a benchmark or network latency."
    )
    file_check_ms: float | None = None
    checkpoints_available: bool | None = Field(
        default=None,
        description="False for a shared SQLite file: unprefixed checkpoints cannot be attributed safely.",
    )
    memory_counts: list[SqliteCountCheck] = Field(default_factory=list)
    checkpoint_counts: list[SqliteCountCheck] = Field(default_factory=list)
    namespace: str | None = None
    namespace_tables: list[NamespaceTableCheck] = Field(default_factory=list)
    cleanup_preview: CleanupPreview | None = None
    file_size: int | None = None
    wal_size: int | None = None
    reclaimable_bytes: int | None = None
    auto_vacuum_enabled: bool | None = None
    page_size: int | None = None
    total_pages: int | None = None
    freelist_pages: int | None = None
    would_reclaim_pages: int | None = None
    tables: list[StorageTableCheck] = Field(default_factory=list)


class StorageJob(BaseModel):
    job_id: str
    backend: str | None = None
    operation: str | None = None
    restored_backup_id: str | None = None
    scope: Literal["agent"]
    phase: str
    started_at: float
    updated_at: float
    backup_path: str | None = None
    file_bytes: int | None = None
    scanned: int | None = None
    total: int | None = None
    error: str | None = None
    report: dict[str, Any] | None = Field(
        default=None,
        description="SQLite file statistics plus inspection_before/inspection_after snapshots, or PostgreSQL namespace cleanup counts and backup details.",
    )


class StorageMaintenanceStatus(BaseModel):
    busy: bool = Field(description="A manual memory job is active on this host.")
    job: StorageJob | None = Field(
        default=None,
        description="This expert's latest page maintenance job; retained until host restart.",
    )


class StartStorageMaintenance(BaseModel):
    confirmed: Literal[True] = Field(
        description="Confirm backup, temporary pause of new turns, and maintenance of this expert only."
    )


class SqliteBackup(BaseModel):
    backup_id: str = Field(
        description="Server-generated sibling filename; arbitrary paths are rejected."
    )
    created_at: float
    size_bytes: int
    kind: Literal["before_restore", "before_maintenance"]


class StorageBackupSelection(BaseModel):
    confirmed: Literal[True]
    backup_id: str = Field(min_length=1, max_length=255)


@router.get(
    "/backups",
    response_model=list[SqliteBackup],
    summary="List this expert's SQLite backups, including before-restore snapshots",
)
async def backups(
    agent_id: str,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    try:
        return await server.app_runtime.agent_registry.memory_slim.backups(
            agent_id, locale=resolve_request_locale(request)
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete(
    "/backups",
    status_code=204,
    summary="Permanently delete one backup belonging to this expert",
    description="Requires explicit confirmation. Rejects shared stores, arbitrary paths and deletion during maintenance or restore. Does not change the active memory database.",
)
async def delete_backup(
    agent_id: str,
    body: StorageBackupSelection,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Response:
    row = require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    try:
        await server.app_runtime.agent_registry.memory_slim.delete_backup(
            agent_id, row.user_id or 0, body.backup_id, locale=resolve_request_locale(request)
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post(
    "/restore",
    response_model=StorageMaintenanceStatus,
    status_code=202,
    summary="Back up the current state and restore this expert's SQLite backup",
    description="Pauses only this expert, validates the selected backup, creates a full safety backup, restores memory/checkpoints and recreates the runtime. Other experts and the control-plane database are not restored.",
)
async def restore(
    agent_id: str,
    body: StorageBackupSelection,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    from octop.api.common.memory_client import invalidate_cached_memory

    row = require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    try:
        result = server.app_runtime.agent_registry.memory_slim.start_restore(
            agent_id, row.user_id or 0, body.backup_id, locale=resolve_request_locale(request)
        )
        invalidate_cached_memory(agent_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/check",
    response_model=StorageInspection,
    summary="Inspect memory storage without changing data",
)
async def check_storage(
    agent_id: str,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    try:
        return await server.app_runtime.agent_registry.memory_slim.inspect_storage(
            agent_id, locale=resolve_request_locale(request)
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/maintenance",
    response_model=StorageMaintenanceStatus,
    summary="Read this expert's maintenance progress and result",
)
async def maintenance_status(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    return server.app_runtime.agent_registry.memory_slim.storage_status(agent_id)


@router.post(
    "/maintenance",
    response_model=StorageMaintenanceStatus,
    status_code=202,
    summary="Back up and maintain only this expert's memory store",
)
async def start_maintenance(
    agent_id: str,
    body: StartStorageMaintenance,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    row = require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    try:
        return server.app_runtime.agent_registry.memory_slim.start_current(
            agent_id, row.user_id or 0, locale=resolve_request_locale(request)
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
