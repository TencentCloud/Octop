"""Remote desktop HTTP status."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from octop.api.deps import current_admin
from octop.infra.desktop.session import active_session_count, session_limit
from octop.infra.desktop.setup import desktop_status
from octop.infra.users.identity import User

router = APIRouter()


@router.get("/desktop/status")
async def get_desktop_status(_user: User = Depends(current_admin)) -> dict[str, object]:
    status = desktop_status()
    return {
        "ok": status.ok,
        "desktop_supported": status.desktop_supported,
        "setup_state": status.setup_state,
        "platform": status.platform,
        "display": status.display,
        "reason": status.reason,
        "install_script": status.install_script,
        "start_command": status.start_command,
        "geometry": status.geometry,
        "permissions_needed": list(status.permissions_needed),
        "vnc_localhost_only": status.vnc_localhost_only,
        "active_sessions": active_session_count(),
        "session_limit": session_limit(),
        "native_capture": status.platform in {"darwin", "windows"},
    }
