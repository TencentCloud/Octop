"""Process-level settings exposed to authenticated clients."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server, require_admin
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


class ExpertVisibilityResponse(BaseModel):
    hide_builtin_experts: bool = Field(
        default=False,
        description="When true, non-admin users do not see built-in expert templates.",
    )
    hide_market: bool = Field(
        default=False,
        description="When true, non-admin users do not see the SkillHub expert market.",
    )


class ExpertVisibilityUpdate(BaseModel):
    hide_builtin_experts: bool = Field(..., description="Hide built-in experts from users.")
    hide_market: bool = Field(..., description="Hide the expert market from users.")


def _expert_visibility(server: Any) -> ExpertVisibilityResponse:
    policy = server.services.settings_repo.get_expert_visibility()
    return ExpertVisibilityResponse(
        hide_builtin_experts=policy["hide_builtin_experts"],
        hide_market=policy["hide_market"],
    )


@router.get(
    "/settings/expert-visibility",
    summary="Expert visibility policy",
    response_model=ExpertVisibilityResponse,
)
async def get_expert_visibility(
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> ExpertVisibilityResponse:
    """Return whether built-in experts / the expert market are hidden from users.

    Readable by any authenticated user so the dashboard can hide the matching
    tabs; the values themselves are only advisory to non-admins (the backend
    still filters the listings).
    """
    return _expert_visibility(server)


@router.put(
    "/settings/expert-visibility",
    summary="Update expert visibility policy (admin)",
    response_model=ExpertVisibilityResponse,
)
async def update_expert_visibility(
    body: ExpertVisibilityUpdate,
    server: Any = Depends(get_server),
    _: Any = Depends(require_admin()),
) -> ExpertVisibilityResponse:
    """Persist the expert-visibility policy. Admin only."""
    server.services.settings_repo.set_expert_visibility(
        hide_builtin_experts=body.hide_builtin_experts,
        hide_market=body.hide_market,
    )
    return _expert_visibility(server)
