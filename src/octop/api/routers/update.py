"""Self-update API — mirrors finnie/octop dashboard update flow."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from octop.api.deps import current_user, require_permission
from octop.api.routers.update_store import (
    UpgradeTaskStatus,
    cache_status,
    create_task,
    get_cached_status,
    get_task,
    update_task,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.setup.self_update import (
    UpgradeResult,
    fetch_latest_pypi_version,
    fetch_pypi_info,
    get_editable_path,
    get_local_version,
    green_packages_dir,
    is_newer,
    parse_changelog_for_version,
    run_upgrade,
)
from octop.infra.setup.service import (
    ServiceRuntime,
    build_runtime,
    detect_service_mode,
    is_service_installed,
    restart_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/update", tags=["update"])


def _build_status(
    *,
    latest: str | None = None,
    error: str | None = None,
    release_notes: str | None = None,
) -> dict[str, Any]:
    current = get_local_version()
    if latest is None and error is None:
        latest = fetch_latest_pypi_version()
    has_update = bool(latest and is_newer(latest, current))
    payload = {
        "current_version": current,
        "latest_version": latest,
        "has_update": has_update,
        "is_editable": get_editable_path() is not None,
        "service_mode": detect_service_mode(),
        "desktop": _is_desktop_process(),
        "error": error,
        "last_check_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "release_notes": release_notes if has_update else None,
    }
    cache_status(payload)
    return payload


@router.get("/status")
async def update_status(_: Any = Depends(current_user)) -> dict[str, Any]:
    """Return last check result; re-probe PyPI when the server cache TTL expires."""
    cached = get_cached_status()
    if cached is not None:
        return cached
    return await asyncio.to_thread(_build_status)


@router.post("/check")
async def check_for_updates(_: Any = Depends(require_permission("update"))) -> dict[str, Any]:
    pypi_info = await asyncio.to_thread(fetch_pypi_info)
    if pypi_info is None:
        return await asyncio.to_thread(_build_status, latest=None, error="could not reach PyPI")
    release_notes = parse_changelog_for_version(pypi_info.description, pypi_info.version)
    return await asyncio.to_thread(
        _build_status, latest=pypi_info.version, release_notes=release_notes
    )


async def _upgrade_worker(task_id: str) -> None:
    await update_task(task_id, stage="downloading", percent=20)
    result: UpgradeResult = await asyncio.to_thread(run_upgrade, verbose=False)
    mirror_errors = result.mirror_errors or None
    if not result.success:
        await update_task(
            task_id,
            status=UpgradeTaskStatus.ERROR,
            stage="error",
            percent=None,
            success=False,
            error=result.error or "upgrade failed",
            mirror_errors=mirror_errors,
        )
        return
    new_version = result.installed_version or fetch_latest_pypi_version()
    await update_task(
        task_id,
        status=UpgradeTaskStatus.COMPLETE,
        stage="complete",
        percent=100,
        new_version=new_version,
        success=True,
        error=None,
        mirror_errors=mirror_errors,
    )


@router.post("/upgrade")
async def trigger_upgrade(_: Any = Depends(require_permission("update"))) -> dict[str, Any]:
    if get_editable_path() is not None:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "editable installs must be upgraded manually (git pull / uv sync)",
        )
    task = await create_task()
    asyncio.create_task(_upgrade_worker(task.task_id))
    return {"task_id": task.task_id, "status": "started"}


@router.get("/progress")
async def upgrade_progress(
    task_id: str = Query(...),
    _: Any = Depends(require_permission("update")),
) -> dict[str, Any]:
    task = await get_task(task_id)
    if task is None:
        raise OctopError(ErrorCode.NOT_FOUND, "upgrade task not found")
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "stage": task.stage,
        "percent": task.percent,
        "new_version": task.new_version,
        "success": task.success,
        "error": task.error,
        "mirror_errors": task.mirror_errors,
    }


def _is_desktop_process() -> bool:
    if green_packages_dir() is not None:
        return True
    raw = (os.environ.get("OCTOP_DESKTOP") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _restart_desktop_process() -> None:
    time.sleep(0.4)
    argv = list(getattr(sys, "orig_argv", None) or [sys.executable, *sys.argv])
    os.execv(argv[0], argv)


def _restart_service_task(runtime: ServiceRuntime) -> None:
    try:
        restart_service(runtime)
    except Exception:
        logger.exception("background service restart failed")


@router.post("/restart")
async def restart_service_endpoint(
    background_tasks: BackgroundTasks,
    _: Any = Depends(require_permission("update")),
) -> dict[str, Any]:
    if _is_desktop_process():
        background_tasks.add_task(_restart_desktop_process)
        return {"status": "restarting", "service_mode": "desktop"}
    mode = detect_service_mode()
    if mode is None:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "service restart is only available when OCTOP_SERVICE_MODE is set",
        )
    try:
        runtime = build_runtime(mode=mode)
        if not is_service_installed(
            runtime.mode,
            scope=runtime.scope,
            run_as_user=runtime.run_as_user,
        ):
            raise RuntimeError(
                f"octop system service is not installed (expected unit for mode={runtime.mode})"
            )
    except RuntimeError as exc:
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc)) from exc
    except Exception as exc:
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc)) from exc
    background_tasks.add_task(_restart_service_task, runtime)
    return {"status": "restarting", "service_mode": mode}
