"""Remote Android HTTP status and agent-control binding."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.mobile.adb import device_info, list_devices
from octop.infra.mobile.agent_control import (
    get_mobile_agent_control,
    set_mobile_agent_control,
)
from octop.infra.mobile.setup import mobile_status
from octop.infra.users.identity import User
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()


class MobileAgentControlBody(BaseModel):
    enabled: bool = Field(description="Whether the agent may use the bound device.")
    device: str | None = Field(
        default=None,
        description="adb serial to bind when enabled (required to turn on).",
    )


def _agent_control_payload() -> dict[str, object]:
    st = get_mobile_agent_control()
    return {"enabled": st.enabled, "device": st.device}


@router.get("/mobile/status", summary="Remote Phone status")
async def get_mobile_status(
    request: Request,
    server: Any = Depends(get_server),
    _user: User = Depends(require_permission("mobile")),
) -> dict[str, object]:
    locale = resolve_request_locale(request)
    status = mobile_status(server.services.config, locale=locale)
    devices = list(status.devices)
    control = get_mobile_agent_control()
    # Drop a stale binding if the phone was unplugged.
    if control.enabled and control.device and control.device not in devices:
        set_mobile_agent_control(enabled=False, device=None)
        control = get_mobile_agent_control()
    return {
        "ok": status.ok,
        "mobile_supported": status.mobile_supported,
        "setup_state": status.setup_state,
        "backend": status.backend,
        "platform": status.platform,
        "reason": status.reason,
        "adb_available": status.adb_available,
        "adb_path": status.adb_path,
        "devices": devices,
        "selected_device": status.selected_device,
        "container_running": status.container_running,
        "agent_control": {
            "enabled": control.enabled,
            "device": control.device,
        },
    }


@router.get(
    "/mobile/devices/{device}/info",
    summary="Probe connected Android device details via adb",
)
async def get_mobile_device_info(
    device: str,
    _user: User = Depends(require_permission("mobile")),
) -> dict[str, object]:
    serial = device.strip()
    if not serial:
        raise HTTPException(status_code=400, detail="device is required")
    # Probe even if briefly missing from ``adb devices`` (USB races while streaming).
    info = await asyncio.to_thread(device_info, serial)
    if info.get("model") is None and info.get("width") is None and info.get("mem_total_mb") is None:
        connected = list_devices()
        if serial not in connected:
            raise HTTPException(status_code=404, detail=f"adb device not connected: {serial}")
    return info


@router.get("/mobile/agent-control", summary="Get agent mobile-device binding")
async def get_agent_control(
    _user: User = Depends(require_permission("mobile")),
) -> dict[str, object]:
    return _agent_control_payload()


@router.put("/mobile/agent-control", summary="Set agent mobile-device binding")
async def put_agent_control(
    body: MobileAgentControlBody,
    _user: User = Depends(require_permission("mobile")),
) -> dict[str, object]:
    if body.enabled:
        devices = list_devices()
        serial = (body.device or "").strip()
        if not serial:
            raise HTTPException(status_code=400, detail="device is required when enabling")
        if serial not in devices:
            raise HTTPException(status_code=400, detail=f"adb device not connected: {serial}")
        set_mobile_agent_control(enabled=True, device=serial)
    else:
        set_mobile_agent_control(enabled=False, device=None)
    return _agent_control_payload()
