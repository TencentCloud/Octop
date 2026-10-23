"""Sandbox container admin router — ledger, drift, recreate (admin)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from octop.api.deps import get_server, require_permission
from octop.infra.backend.sandbox_admin import SandboxAdminService
from octop.infra.errors import ErrorCode, OctopError

admin_router = APIRouter(tags=["sandbox-admin"])


def _service(server: Any) -> SandboxAdminService:
    assert server.app_runtime is not None
    return SandboxAdminService(services=server.services, app_runtime=server.app_runtime)


class RecreateResponse(BaseModel):
    recreated: bool
    container_name: str
    backup_path: str
    old_image: str | None = None
    expected_image: str | None = None
    old_network_offline: bool | None = None
    expected_allow_network: bool | None = None


@admin_router.get(
    "",
    summary="List sandbox containers",
    description=(
        "Ledger of all local containers carrying the harness sandbox label, with "
        "image/network drift against the configured expected values."
    ),
)
async def list_sandboxes(
    _: Any = Depends(require_permission("storage_backends")),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    return [asdict(e) for e in _service(server).list_sandboxes()]


@admin_router.post(
    "/{container_name}/recreate",
    response_model=RecreateResponse,
    summary="Recreate a sandbox container",
    description=(
        "Back up the container workspace to the host, verify the expected image "
        "exists, then remove the container. The next conversation recreates it "
        "with the configured image and network mode. Refused with 409 while an "
        "affected expert has an active conversation."
    ),
)
async def recreate_sandbox(
    container_name: str,
    _: Any = Depends(require_permission("storage_backends")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return _service(server).recreate(container_name)


@admin_router.get(
    "/images",
    summary="List local Docker images",
    description="Local images with size and sandbox-reference flags.",
)
async def list_sandbox_images(
    _: Any = Depends(require_permission("storage_backends")),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    return _service(server).list_images()


@admin_router.get(
    "/backups/{container_name}",
    summary="List workspace backups of a sandbox container",
)
async def list_sandbox_backups(
    container_name: str,
    _: Any = Depends(require_permission("storage_backends")),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    if not container_name.strip():
        raise OctopError(ErrorCode.SANDBOX_CONTAINER_NOT_FOUND, "empty container name")
    return _service(server).list_backups(container_name)
