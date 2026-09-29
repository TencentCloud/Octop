"""API endpoints for Ollama model management.

This router delegates lifecycle operations
(list / pull / delete) to the Ollama daemon via OllamaModelManager. Downloads
run in the background and their status can be polled by the frontend.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.api.routers.ollama_download_store import (
    DownloadTask,
    DownloadTaskStatus,
    cancel_task,
    clear_completed,
    create_task,
    get_tasks,
    update_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ollama-models", tags=["ollama"])


class OllamaDownloadRequest(BaseModel):
    name: str = Field(..., description="Ollama model name, e.g. 'llama3:8b'")


class OllamaModelResponse(BaseModel):
    name: str
    size: int
    digest: str | None = None
    modified_at: str | None = None


class OllamaDownloadTaskResponse(BaseModel):
    task_id: str
    status: str
    name: str
    error: str | None = None
    result: OllamaModelResponse | None = None


def _is_ollama_connection_error(exc: Exception) -> bool:
    """Return True when the exception indicates Ollama daemon is unreachable."""
    if isinstance(exc, ConnectionError):
        return True
    msg = str(exc).lower()
    return "failed to connect to ollama" in msg or "connection refused" in msg


def _task_to_response(task: DownloadTask) -> OllamaDownloadTaskResponse:
    result = None
    if task.result:
        result = OllamaModelResponse(**task.result)
    return OllamaDownloadTaskResponse(
        task_id=task.task_id,
        status=task.status.value,
        name=task.repo_id,
        error=task.error,
        result=result,
    )


@router.get(
    "",
    response_model=list[OllamaModelResponse],
    summary="List Ollama models",
)
async def list_ollama_models(
    server: Any = Depends(get_server),
    _: Any = Depends(require_permission("ollama_models")),
) -> list[OllamaModelResponse]:
    """Return models from the Ollama daemon and/or the configured models dir."""
    from octop.infra.utils.ollama_manager import (
        OllamaModelInfo,
        OllamaModelManager,
        apply_models_dir,
        is_ollama_reachable,
        list_models_from_dir,
        merge_model_lists,
    )

    models_dir = _ollama_models_dir(server)
    apply_models_dir(models_dir or None)
    disk_models = list_models_from_dir(models_dir) if models_dir else []

    api_models: list[OllamaModelInfo] = []
    api_exc: Exception | None = None
    service_on = _ollama_service_enabled(server)
    daemon_up = False
    if not service_on:
        try:
            daemon_up = is_ollama_reachable()
        except Exception:
            daemon_up = False
    if service_on or daemon_up:
        try:
            api_models = OllamaModelManager.list_models(start_if_needed=service_on)
        except (OSError, ImportError) as exc:
            api_exc = exc
            logger.warning("Ollama bootstrap failed: %s", exc)
        except Exception as exc:
            api_exc = exc
            if _is_ollama_connection_error(exc):
                logger.warning(
                    "Failed to connect to Ollama while listing models: %s",
                    exc,
                )
            else:
                logger.exception("Failed to list Ollama models")

    models = merge_model_lists(api_models, disk_models)
    if models:
        return [OllamaModelResponse(**m.model_dump()) for m in models]

    if api_exc is not None:
        if isinstance(api_exc, OSError | ImportError) or _is_ollama_connection_error(api_exc):
            raise HTTPException(
                status_code=503,
                detail=(
                    str(api_exc)
                    if isinstance(api_exc, OSError | ImportError)
                    else "Failed to connect to Ollama. Please ensure Ollama is installed and running."
                ),
            ) from api_exc
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list Ollama models: {api_exc}",
        ) from api_exc

    if not _ollama_service_enabled(server):
        raise HTTPException(
            status_code=503,
            detail="Ollama service is disabled. Enable it from the provider card.",
        )
    return []


@router.post(
    "/download",
    response_model=OllamaDownloadTaskResponse,
    summary="Start a background Ollama model pull",
)
async def download_ollama_model(
    body: OllamaDownloadRequest,
    server: Any = Depends(get_server),
    _: Any = Depends(require_permission("ollama_models")),
) -> OllamaDownloadTaskResponse:
    """Start a background pull via Ollama SDK.

    Returns a task_id immediately; the frontend can poll /download-status
    to track progress.
    """
    from octop.infra.utils.ollama_manager import apply_models_dir

    apply_models_dir(_ollama_models_dir(server) or None)
    await clear_completed(backend="ollama")

    task = await create_task(
        repo_id=body.name,
        filename=None,
        backend="ollama",
        source="ollama",
    )

    loop = asyncio.get_running_loop()
    asyncio.create_task(
        _run_pull_in_background(task.task_id, body.name, loop),
        name=f"ollama-download-{task.task_id}",
    )

    return _task_to_response(task)


async def _run_pull_in_background(
    task_id: str,
    name: str,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Execute the Ollama pull in a thread and update task status."""
    from octop.infra.utils.ollama_manager import OllamaModelInfo, OllamaModelManager

    await update_status(task_id, DownloadTaskStatus.DOWNLOADING)

    try:
        info: OllamaModelInfo = await loop.run_in_executor(
            None,
            lambda: OllamaModelManager.pull_model(name),
        )
        result_dict = info.model_dump()
        await update_status(
            task_id,
            DownloadTaskStatus.COMPLETED,
            result=result_dict,
        )
    except Exception as exc:
        logger.exception("Ollama model pull failed: %s", exc)
        await update_status(
            task_id,
            DownloadTaskStatus.FAILED,
            error=str(exc),
        )


@router.get(
    "/download-status",
    response_model=list[OllamaDownloadTaskResponse],
    summary="Get Ollama download tasks",
)
async def get_ollama_download_status(
    _: Any = Depends(require_permission("ollama_models")),
) -> list[OllamaDownloadTaskResponse]:
    """Return all Ollama-related download tasks."""
    tasks = await get_tasks(backend="ollama")
    return [_task_to_response(t) for t in tasks]


@router.delete(
    "/download/{task_id}",
    summary="Cancel an Ollama download task",
)
async def cancel_ollama_download(
    task_id: str,
    _: Any = Depends(require_permission("ollama_models")),
) -> dict[str, Any]:
    """Cancel a pending or downloading Ollama model pull."""
    success = await cancel_task(task_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found or not cancellable",
        )
    return {"status": "cancelled", "task_id": task_id}


@router.delete(
    "/{name:path}",
    summary="Delete an Ollama model",
)
async def delete_ollama_model(
    name: str,
    server: Any = Depends(get_server),
    _: Any = Depends(require_permission("ollama_models")),
) -> dict[str, Any]:
    """Delete an Ollama model via the SDK."""
    try:
        from octop.infra.utils.ollama_manager import OllamaModelManager, apply_models_dir

        apply_models_dir(_ollama_models_dir(server) or None)
    except (OSError, ImportError) as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    try:
        OllamaModelManager.delete_model(name)
    except Exception as exc:
        logger.exception("Failed to delete Ollama model: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "deleted", "name": name}


_SETTINGS_KEY_OLLAMA_SERVICE = "ollama_service_enabled"


class OllamaServiceBody(BaseModel):
    enabled: bool | None = Field(
        default=None,
        description="Whether Octop should keep the Ollama service running. Omit to leave unchanged.",
    )
    models_dir: str | None = Field(
        default=None,
        description=(
            "Absolute Ollama models directory (OLLAMA_MODELS). "
            "Omit to leave unchanged; empty string clears the override."
        ),
    )


class OllamaServiceStatus(BaseModel):
    enabled: bool
    running: bool
    models_dir: str = Field("", description="Configured Ollama models directory, empty if unset")


def _ollama_service_enabled(server: Any) -> bool:
    raw = server.services.settings_repo.get(_SETTINGS_KEY_OLLAMA_SERVICE)
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _ollama_models_dir(server: Any) -> str:
    from octop.infra.utils.ollama_manager import SETTINGS_KEY_MODELS_DIR

    raw = server.services.settings_repo.get(SETTINGS_KEY_MODELS_DIR)
    return (raw or "").strip()


def _service_status(server: Any, *, enabled: bool, running: bool) -> OllamaServiceStatus:
    return OllamaServiceStatus(
        enabled=enabled,
        running=running,
        models_dir=_ollama_models_dir(server),
    )


@router.get(
    "/service",
    response_model=OllamaServiceStatus,
    summary="Get Ollama local service status",
)
async def get_ollama_service(
    server: Any = Depends(get_server),
    _: Any = Depends(require_permission("ollama_models")),
) -> OllamaServiceStatus:
    from octop.infra.utils.ollama_manager import is_ollama_reachable

    enabled = _ollama_service_enabled(server)
    running = False
    try:
        running = is_ollama_reachable()
    except Exception:
        running = False
    return _service_status(server, enabled=enabled, running=running)


@router.put(
    "/service",
    response_model=OllamaServiceStatus,
    summary="Update Ollama local service",
    description=(
        "Toggle the managed daemon and/or set the models directory. "
        "Omit enabled to change models_dir without stopping a running service."
    ),
)
async def put_ollama_service(
    body: OllamaServiceBody,
    server: Any = Depends(get_server),
    _: Any = Depends(require_permission("ollama_models")),
) -> OllamaServiceStatus:
    from octop.infra.utils.ollama_manager import (
        SETTINGS_KEY_MODELS_DIR,
        apply_models_dir,
        is_ollama_reachable,
        normalize_models_dir,
        start_ollama_service,
        stop_ollama_service,
    )

    previous_dir = _ollama_models_dir(server)
    models_dir_changed = False
    if body.models_dir is not None:
        try:
            normalized = normalize_models_dir(body.models_dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        server.services.settings_repo.set(SETTINGS_KEY_MODELS_DIR, normalized)
        models_dir_changed = normalized != previous_dir

    apply_models_dir(_ollama_models_dir(server) or None)

    enabled = _ollama_service_enabled(server)
    if body.enabled is not None:
        enabled = body.enabled
        server.services.settings_repo.set(
            _SETTINGS_KEY_OLLAMA_SERVICE,
            "true" if enabled else "false",
        )

    if body.enabled is None:
        # Directory-only update: restart only if the daemon is already managed on.
        if models_dir_changed and enabled:
            stop_ollama_service()
            try:
                start_ollama_service()
            except Exception as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
    elif enabled:
        if models_dir_changed:
            stop_ollama_service()
        try:
            start_ollama_service()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    else:
        stop_ollama_service()
    return _service_status(
        server,
        enabled=enabled,
        running=is_ollama_reachable(),
    )
