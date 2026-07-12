"""Desktop environment installation (SSE)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from octop.api.deps import current_admin
from octop.infra.desktop.setup import install_desktop_stream
from octop.infra.users.identity import User

router = APIRouter()


@router.post("/desktop/install")
async def install_desktop(_user: User = Depends(current_admin)) -> StreamingResponse:
    """Stream virtual desktop installation progress as SSE (admin only).

    Installs Python extras when missing, then runs the Linux system install
    or start script when the host has no graphical display.
    """

    async def _event_stream() -> AsyncGenerator[str, None]:
        async for event in install_desktop_stream():
            yield event

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
