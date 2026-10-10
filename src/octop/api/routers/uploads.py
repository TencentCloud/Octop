"""Dashboard chat attachments — stored in agent workspace ``inbound/``."""

from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from octop.api.common.agent import require_agent_row, user_owns_agent
from octop.api.common.attachments import (
    StoredAttachment,
    dashboard_inbound_preview_url,
    save_attachment,
)
from octop.api.common.upload_limit import read_upload_capped
from octop.api.common.workspace import require_running_workspace
from octop.api.deps import current_user, get_server
from octop.config import DEFAULT_MAX_UPLOAD_MB, upload_mb_to_bytes
from octop.infra.desktop.native_capture import (
    CaptureMode,
    capture_available,
    capture_from_composer,
)
from octop.infra.gateway.media.attachment_hints import sniff_image_media_type
from octop.infra.gateway.media.inbound_store import INBOUND_EXTENSION_MEDIA_TYPES

router = APIRouter()


class CaptureAttachment(BaseModel):
    path: str
    workspace_path: str
    filename: str
    media_type: str
    url: str
    access_url: str
    preview_url: str | None = None


class CaptureAvailability(BaseModel):
    available: bool = False


class CaptureRequest(BaseModel):
    mode: CaptureMode = "scan"


class CaptureResponse(BaseModel):
    status: Literal["ok", "cancelled", "timeout", "unavailable", "error", "busy"]
    attachments: list[CaptureAttachment]


@router.get(
    "/agents/{agent_id}/native-capture",
    summary="Check iPhone capture availability for the chat composer",
    response_model=CaptureAvailability,
)
async def native_capture_available(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> CaptureAvailability:
    row = require_agent_row(agent_id, user=user, as_user=None, server=server)
    if not user.is_admin and not user_owns_agent(row, user):
        return CaptureAvailability()
    available = await asyncio.to_thread(capture_available)
    return CaptureAvailability(available=available)


@router.post(
    "/agents/{agent_id}/native-capture",
    summary="Capture iPhone scans or photos as pending chat attachments",
    description="Owner/admin only. Opens native UI on the macOS server. Waits up to ten minutes for user capture; no model invocation or message is sent.",
    response_model=CaptureResponse,
)
async def native_capture_attachment(
    agent_id: str,
    body: CaptureRequest | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> CaptureResponse:
    workspace = await require_running_workspace(
        agent_id, user=user, as_user=None, server=server, owner_only=True
    )
    result = await capture_from_composer(
        workspace,
        body.mode if body else "scan",
        max_bytes=int(server.services.config.max_upload_bytes) if server.services else None,
    )
    attachments = []
    for file in result.get("files", []):
        stored = StoredAttachment(
            filename=file["filename"],
            media_type=file["media_type"],
            size=file["size"],
            data_path=file["path"],
        )
        payload = _attachment_payload(agent_id, stored)
        if preview_path := file.get("preview_path"):
            payload["preview_url"] = dashboard_inbound_preview_url(
                agent_id, preview_path, media_type="image/png"
            )
        attachments.append(CaptureAttachment.model_validate(payload))
    return CaptureResponse(status=result["status"], attachments=attachments)


def _resolve_media_type(filename: str, content_type: str | None, data: bytes = b"") -> str:
    raw = (content_type or "").split(";", 1)[0].strip().lower()
    if raw and raw != "application/octet-stream":
        return raw
    ext = Path(filename or "").suffix.lower()
    if ext in INBOUND_EXTENSION_MEDIA_TYPES:
        return INBOUND_EXTENSION_MEDIA_TYPES[ext]
    guessed, _ = mimetypes.guess_type(filename or "")
    if guessed:
        return guessed.lower()
    sniffed = sniff_image_media_type(data)
    if sniffed:
        return sniffed
    return "application/octet-stream"


def _attachment_payload(agent_id: str, stored: StoredAttachment) -> dict[str, str]:
    path = stored.data_path
    preview_url = dashboard_inbound_preview_url(
        agent_id,
        path,
        media_type=stored.media_type,
    )
    return {
        "path": path,
        "workspace_path": path,
        "url": preview_url,
        "access_url": preview_url,
        "filename": stored.filename,
        "media_type": stored.media_type,
    }


@router.post("/agents/{agent_id}/upload", summary="Upload a chat attachment")
async def upload_attachment(
    agent_id: str,
    file: UploadFile = File(...),  # noqa: B008
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, str]:
    ws = await require_running_workspace(agent_id, user=user, as_user=as_user, server=server)
    max_bytes = (
        int(server.services.config.max_upload_bytes) if server.services is not None else None
    )
    fallback = upload_mb_to_bytes(DEFAULT_MAX_UPLOAD_MB)
    data = await read_upload_capped(file, max_bytes=max_bytes or fallback)
    filename = file.filename or "upload.bin"
    media_type = _resolve_media_type(filename, file.content_type, data)
    stored = await save_attachment(
        ws,
        owner_id=user.id,
        filename=filename,
        media_type=media_type,
        data=data,
        max_bytes=max_bytes,
    )
    return _attachment_payload(agent_id, stored)
