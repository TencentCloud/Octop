"""Office preview runtime probe."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends

from octop.api.deps import current_user
from octop.infra.office_preview.service import get_office_preview_service

router = APIRouter()


@router.get(
    "/office-preview/status",
    summary="Probe the Office-to-PDF preview runtime",
    description=(
        "Returns whether the optional LibreOffice Kit helper is installed. "
        "The default wheel does not bundle the engine; run ``octop office-preview install``."
    ),
)
async def office_preview_status(_: Any = Depends(current_user)) -> dict[str, Any]:
    return await asyncio.to_thread(get_office_preview_service().status)
