"""Service control API — installed version and in-process restart.

Replaces the self-update chain (`octop.api.routers.update`) in the router mount: that
module stays in the tree but is not registered, so no public package index is reachable.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends

from octop.api.deps import current_user, get_server, require_permission
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer
from octop.infra.setup.self_update import get_local_version, green_packages_dir
from octop.infra.setup.service import (
    ServiceRuntime,
    build_runtime,
    detect_service_mode,
    is_service_installed,
    restart_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/update", tags=["update"])


def is_desktop_process() -> bool:
    """True when hosted by the Wails desktop shell (or a green portable install)."""
    if green_packages_dir() is not None:
        return True
    raw = (os.environ.get("AGENTBUDDY_DESKTOP") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


@router.get("/status")
async def service_status(_: Any = Depends(current_user)) -> dict[str, Any]:
    """Installed version and restart capability — never contacts a package index."""
    return {
        "current_version": get_local_version(),
        "service_mode": detect_service_mode(),
        "desktop": is_desktop_process(),
    }


def _restart_desktop_process(server: OctopServer) -> None:
    time.sleep(0.4)

    # Flush SQLite WAL before replacing the process image, otherwise uncheckpointed
    # writes (common in WAL mode) are lost when the connection FD is closed by execv.
    if server.services is not None and getattr(server.services.db, "dialect", None) == "sqlite":
        try:
            with server.services.db.connect() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            server.services.db.close()
        except Exception:
            logger.exception("failed to checkpoint/close database before desktop restart")

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
    server: OctopServer = Depends(get_server),
    _: Any = Depends(require_permission("update")),
) -> dict[str, Any]:
    if is_desktop_process():
        background_tasks.add_task(_restart_desktop_process, server)
        return {"status": "restarting", "service_mode": "desktop"}
    mode = detect_service_mode()
    if mode is None:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "service restart is only available when AGENTBUDDY_SERVICE_MODE is set",
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
