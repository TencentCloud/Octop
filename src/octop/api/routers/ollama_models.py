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

from octop.api.deps import current_admin, current_user, get_server
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
    _: Any = Depends(current_user),
) -> list[OllamaModelResponse]:
    """Return the current Ollama model list via the SDK."""
    if not _ollama_service_enabled(server):
        raise HTTPException(
            status_code=503,
            detail="Ollama service is disabled. Enable it from the provider card.",
        )
    try:
        from octop.infra.utils.ollama_manager import OllamaModelManager

        models = OllamaModelManager.list_models()
    except (OSError, ImportError) as exc:
        logger.warning("Ollama bootstrap failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        if _is_ollama_connection_error(exc):
            logger.warning(
                "Failed to connect to Ollama while listing models: %s",
                exc,
            )
            raise HTTPException(
                status_code=503,
                detail="Failed to connect to Ollama. Please ensure Ollama is installed and running.",
            ) from exc
        logger.exception("Failed to list Ollama models")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list Ollama models: {exc}",
        ) from exc

    return [OllamaModelResponse(**m.model_dump()) for m in models]


@router.post(
    "/download",
    response_model=OllamaDownloadTaskResponse,
    summary="Start a background Ollama model pull",
)
async def download_ollama_model(
    body: OllamaDownloadRequest,
    _: Any = Depends(current_user),
) -> OllamaDownloadTaskResponse:
    """Start a background pull via Ollama SDK.

    Returns a task_id immediately; the frontend can poll /download-status
    to track progress.
    """
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
    _: Any = Depends(current_user),
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
    _: Any = Depends(current_user),
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
    _: Any = Depends(current_user),
) -> dict[str, Any]:
    """Delete an Ollama model via the SDK."""
    try:
        from octop.infra.utils.ollama_manager import OllamaModelManager
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
    enabled: bool = Field(..., description="Whether Octop should keep the Ollama service running")


class OllamaServiceStatus(BaseModel):
    enabled: bool
    running: bool


def _ollama_service_enabled(server: Any) -> bool:
    raw = server.services.settings_repo.get(_SETTINGS_KEY_OLLAMA_SERVICE)
    if raw is None:
        return True  # default on for backward compatibility
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@router.get(
    "/service",
    response_model=OllamaServiceStatus,
    summary="Get Ollama local service status",
)
async def get_ollama_service(
    server: Any = Depends(get_server),
    _: Any = Depends(current_user),
) -> OllamaServiceStatus:
    from octop.infra.utils.ollama_manager import is_ollama_reachable

    enabled = _ollama_service_enabled(server)
    running = False
    try:
        running = is_ollama_reachable()
    except Exception:
        running = False
    return OllamaServiceStatus(enabled=enabled, running=running)


@router.put(
    "/service",
    response_model=OllamaServiceStatus,
    summary="Enable/disable Ollama local service",
)
async def put_ollama_service(
    body: OllamaServiceBody,
    server: Any = Depends(get_server),
    _: Any = Depends(current_admin),
) -> OllamaServiceStatus:
    from octop.infra.utils.ollama_manager import (
        is_ollama_reachable,
        start_ollama_service,
        stop_ollama_service,
    )

    server.services.settings_repo.set(
        _SETTINGS_KEY_OLLAMA_SERVICE,
        "true" if body.enabled else "false",
    )
    if body.enabled:
        try:
            start_ollama_service()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    else:
        stop_ollama_service()
    return OllamaServiceStatus(
        enabled=body.enabled,
        running=is_ollama_reachable(),
    )
