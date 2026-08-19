"""Remote Android HTTP status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from octop.api.deps import get_server, require_permission
from octop.infra.mobile.setup import mobile_status
from octop.infra.users.identity import User
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()


@router.get("/mobile/status")
async def get_mobile_status(
    request: Request,
    server: Any = Depends(get_server),
    _user: User = Depends(require_permission("mobile")),
) -> dict[str, object]:
    locale = resolve_request_locale(request)
    status = mobile_status(server.services.config, locale=locale)
    return {
        "ok": status.ok,
        "mobile_supported": status.mobile_supported,
        "setup_state": status.setup_state,
        "backend": status.backend,
        "platform": status.platform,
        "reason": status.reason,
        "adb_available": status.adb_available,
        "adb_path": status.adb_path,
        "devices": list(status.devices),
        "selected_device": status.selected_device,
        "container_running": status.container_running,
    }
