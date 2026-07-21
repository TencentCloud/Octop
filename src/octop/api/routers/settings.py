"""Process-level settings exposed to authenticated clients."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server

router = APIRouter()


class TimezoneSettingsResponse(BaseModel):
    timezone: str = Field(description="IANA timezone from config ``default_timezone``.")


@router.get(
    "/settings/timezone",
    summary="Server default timezone",
    response_model=TimezoneSettingsResponse,
)
async def get_timezone_settings(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> TimezoneSettingsResponse:
    """Return the process default timezone used for display and scheduling."""
    return TimezoneSettingsResponse(timezone=server.services.config.default_timezone)
