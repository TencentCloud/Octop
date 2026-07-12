"""Desktop environment uninstallation (SSE)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from octop.api.deps import current_admin
from octop.infra.desktop.setup import uninstall_desktop_stream
from octop.infra.users.identity import User
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()


@router.post("/desktop/uninstall")
async def uninstall_desktop(
    request: Request,
    _user: User = Depends(current_admin),
) -> StreamingResponse:
    """Stream virtual desktop uninstall progress as SSE (admin only)."""
    locale = resolve_request_locale(request)

    async def _event_stream() -> AsyncGenerator[str, None]:
        async for event in uninstall_desktop_stream(locale=locale):
            yield event

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
