"""Storage backends router — admin-only."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from octop.api.deps import current_admin, current_user, get_server
from octop.infra.backend.adapter import row_to_backend_spec
from octop.infra.backend.docker_spec import docker_spec_previewable
from octop.infra.errors import ErrorCode, OctopError

admin_router = APIRouter()


class StorageBackendCreateBody(BaseModel):
    name: str
    kind: str
    endpoint: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    bucket: str | None = None
    region: str | None = None
    config_json: str | None = None
    note: str | None = None


class StorageBackendPatchBody(BaseModel):
    kind: str | None = None
    endpoint: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    bucket: str | None = None
    region: str | None = None
    config_json: str | None = None
    note: str | None = None
    enabled: bool | None = None


class StorageBackendProbeBody(BaseModel):
    kind: str
    endpoint: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    bucket: str | None = None
    region: str | None = None
    config_json: str | None = None
    """When set, blank secrets in the body are taken from the stored backend."""
    backend_id: int | None = None


def _row_to_dict(r: Any) -> dict[str, Any]:
    """Serialize a BackendRow to API response dict.

    secret_key is intentionally omitted from responses.
    access_key is masked (first 4 chars + asterisks).
    """
    ak = r.access_key or ""
    masked_ak = f"{ak[:4]}{'*' * 8}" if len(ak) > 4 else "*" * len(ak)
    spec = row_to_backend_spec(r)
    return {
        "id": r.id,
        "name": r.name,
        "kind": r.kind,
        "endpoint": r.endpoint,
        "access_key": masked_ak if ak else None,
        "bucket": r.bucket,
        "region": r.region,
        "config_json": r.config_json,
        "note": r.note,
        "enabled": bool(r.enabled),
        "previewable": docker_spec_previewable(spec) if spec is not None else False,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


@admin_router.get("")
async def list_storage_backends(
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in server.services.storage_backend_repo.list_all()]


@admin_router.post("", status_code=201)
async def create_storage_backend(
    body: StorageBackendCreateBody,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    if server.services.storage_backend_repo.get_by_name(body.name) is not None:
        raise OctopError(ErrorCode.STORAGE_BACKEND_NAME_TAKEN, f"name {body.name!r} already exists")
    bid = server.services.storage_backend_repo.create(
        name=body.name,
        kind=body.kind,
        endpoint=body.endpoint,
        access_key=body.access_key,
        secret_key=body.secret_key,
        bucket=body.bucket,
        region=body.region,
        config_json=body.config_json,
        note=body.note,
    )
    return _row_to_dict(server.services.storage_backend_repo.get(bid))


@admin_router.patch("/{backend_id}")
async def patch_storage_backend(
    backend_id: int,
    body: StorageBackendPatchBody,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    row = server.services.storage_backend_repo.get(backend_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "storage backend not found")
    server.services.storage_backend_repo.update(
        backend_id,
        kind=body.kind,
        endpoint=body.endpoint,
        access_key=body.access_key,
        secret_key=body.secret_key,
        bucket=body.bucket,
        region=body.region,
        config_json=body.config_json,
        note=body.note,
        enabled=body.enabled,
    )
    return _row_to_dict(server.services.storage_backend_repo.get(backend_id))


@admin_router.delete("/{backend_id}", status_code=204)
async def delete_storage_backend(
    backend_id: int,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> None:
    row = server.services.storage_backend_repo.get(backend_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "storage backend not found")
    assert server.app_runtime is not None
    refs = server.app_runtime.agent_registry.find_agents_using_storage_backend(row.name)
    if refs:
        raise OctopError(
            ErrorCode.STORAGE_BACKEND_REFERENCED,
            f"storage backend {row.name!r} is referenced by {len(refs)} agent(s)",
            details={"agents": refs},
        )
    server.services.storage_backend_repo.delete(backend_id)


@admin_router.post("/probe")
async def probe_storage_backend_config(
    body: StorageBackendProbeBody,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Probe connectivity from unsaved form values (optional merge with stored row)."""
    from octop.infra.backend.probe import probe_storage_backend, row_for_probe

    base = None
    if body.backend_id is not None:
        base = server.services.storage_backend_repo.get(body.backend_id)
        if base is None:
            raise OctopError(ErrorCode.NOT_FOUND, "storage backend not found")
    row = row_for_probe(
        kind=body.kind,
        endpoint=body.endpoint,
        access_key=body.access_key,
        secret_key=body.secret_key,
        bucket=body.bucket,
        region=body.region,
        config_json=body.config_json,
        base=base,
    )
    return probe_storage_backend(row)


@admin_router.get("/{backend_id}/tree")
async def list_storage_backend_tree(
    backend_id: int,
    path: str = "/",
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """Single-level directory listing for a configured storage backend."""
    row = server.services.storage_backend_repo.get(backend_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "storage backend not found")
    from octop.infra.backend.browse import list_storage_backend_tree as _list_tree

    try:
        return await _list_tree(row, path)
    except ValueError as exc:
        raise OctopError(ErrorCode.WORKSPACE_OP_UNSUPPORTED, str(exc)) from exc


@admin_router.post("/{backend_id}/test")
async def test_storage_backend(
    backend_id: int,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Best-effort connectivity / configuration probe for one backend."""
    row = server.services.storage_backend_repo.get(backend_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "storage backend not found")
    from octop.infra.backend.probe import probe_storage_backend

    return probe_storage_backend(row)


user_router = APIRouter()


@user_router.get("")
async def list_storage_backends_for_user(
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """Read-only storage backend list for regular users (secrets masked)."""
    return [_row_to_dict(r) for r in server.services.storage_backend_repo.list_all()]
