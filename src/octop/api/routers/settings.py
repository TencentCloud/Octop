"""Process-level settings exposed to authenticated clients."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server
from octop.config import OctopConfig

router = APIRouter()


class TimezoneSettingsResponse(BaseModel):
    timezone: str = Field(description="IANA timezone from config ``default_timezone``.")


class UploadSettingsResponse(BaseModel):
    max_upload_mb: int = Field(description="Max upload size in MiB from config ``max_upload_mb``.")
    max_upload_bytes: int = Field(description="Max upload size in bytes.")


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


@router.get(
    "/settings/upload",
    summary="Server upload size limit",
    response_model=UploadSettingsResponse,
)
async def get_upload_settings(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> UploadSettingsResponse:
    """Return the process upload size limit used for chat attachments and knowledge documents."""
    _ = user
    cfg: OctopConfig = server.services.config
    return UploadSettingsResponse(
        max_upload_mb=cfg.max_upload_mb,
        max_upload_bytes=cfg.max_upload_bytes,
    )


class MobileCapabilitiesResponse(BaseModel):
    enabled: bool = Field(description="Whether Remote Android is enabled on this host.")
    backend: str = Field(description="Host backend: physical, redroid, emulator, or none.")


class CapabilitiesResponse(BaseModel):
    mobile: MobileCapabilitiesResponse


@router.get(
    "/settings/capabilities",
    summary="Host feature capabilities",
    response_model=CapabilitiesResponse,
)
async def get_capabilities(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> CapabilitiesResponse:
    """Return install-time host capabilities (always available when authenticated)."""
    _ = user
    cfg: OctopConfig = server.services.config
    cap = cfg.capabilities.mobile
    return CapabilitiesResponse(
        mobile=MobileCapabilitiesResponse(enabled=cap.enabled, backend=cap.backend)
    )
