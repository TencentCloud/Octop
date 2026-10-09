"""Voice STT/TTS router."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from octop.api.deps import current_user, get_server, require_permission
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.locale import resolve_request_locale
from octop.infra.voice.manager import VoiceManager
from octop.infra.voice.presets import load_voice_presets

router = APIRouter()
admin_router = APIRouter()


def _voice_manager(server: Any) -> VoiceManager:
    return VoiceManager(
        settings_repo=server.services.settings_repo,
        voice_provider_repo=server.services.voice_provider_repo,
    )


def _row_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "kind": r.kind,
        "capability": r.capability,
        "base_url": r.base_url,
        "api_key": r.api_key,
        "extra": r.get_extra(),
        "note": r.note,
        "enabled": bool(r.enabled),
    }


VoiceKind = Literal["browser", "edge", "tencent", "openai", "mimo", "dashscope"]
VoiceCapability = Literal["stt", "tts", "both"]


def _validate_extra_json(value: str) -> str:
    if not isinstance(json.loads(value), dict):
        raise ValueError("extra_json must contain a JSON object")
    return value


VoiceExtraJson = Annotated[str, AfterValidator(_validate_extra_json)]


class VoiceProviderCreateBody(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    kind: VoiceKind = Field(description="API protocol; openai supports compatible services.")
    capability: VoiceCapability
    base_url: str | None = Field(default=None, description="Provider HTTPS API base URL.")
    api_key: str | None = None
    extra_json: VoiceExtraJson | None = Field(
        default=None,
        description="JSON object with stt_model, tts_model and voice_id; legacy model is supported.",
    )
    note: str | None = None


class VoiceProviderPatchBody(BaseModel):
    kind: VoiceKind | None = None
    capability: VoiceCapability | None = None
    base_url: str | None = None
    api_key: str | None = None
    extra_json: VoiceExtraJson | None = None
    note: str | None = None
    enabled: bool | None = None


class ActiveVoiceBody(BaseModel):
    stt: str | None = None
    tts: str | None = None


class TTSBody(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    voice_id: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    provider: str | None = None


class VoiceTestBody(BaseModel):
    mode: Literal["stt", "tts"] = "tts"


class VoiceConfigurationTestBody(VoiceProviderCreateBody):
    mode: Literal["stt", "tts"] = "tts"


class VoiceProviderResponse(BaseModel):
    id: int
    name: str
    kind: str
    capability: VoiceCapability
    base_url: str | None
    api_key: str | None
    extra: dict[str, Any]
    note: str | None
    enabled: bool


@router.get("/presets")
async def list_voice_presets(_: Any = Depends(current_user)) -> list[dict[str, Any]]:
    return load_voice_presets()


@router.get(
    "/providers",
    summary="List configured voice providers",
    response_model=list[VoiceProviderResponse],
)
async def list_voice_providers(
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in server.services.voice_provider_repo.list_all()]


@router.get("/active")
async def get_active_voice(
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, str]:
    return _voice_manager(server).get_active()


@router.put("/active")
async def set_active_voice(
    body: ActiveVoiceBody,
    _: Any = Depends(require_permission("voice")),
    server: Any = Depends(get_server),
) -> dict[str, str]:
    return _voice_manager(server).set_active(stt=body.stt, tts=body.tts)


@router.post("/stt")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: str = Form(default="zh-CN"),
    provider: str | None = Form(default=None),
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    data = await audio.read()
    if not data:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "audio file is empty")
    mime = audio.content_type or "audio/webm"
    result = await _voice_manager(server).transcribe(
        data,
        mime=mime,
        language=language,
        provider_name=provider,
    )
    return {"text": result.text, "confidence": result.confidence}


@router.post("/tts")
async def synthesize_speech(
    body: TTSBody,
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    mgr = _voice_manager(server)

    async def _stream() -> AsyncIterator[bytes]:
        async for chunk in mgr.synthesize(
            body.text,
            voice_id=body.voice_id,
            speed=body.speed,
            provider_name=body.provider,
        ):
            yield chunk

    # Mimo and DashScope stream WAV (24kHz PCM16LE); other providers stream MP3.
    return StreamingResponse(_stream(), media_type=mgr.media_type(body.provider))


@admin_router.get(
    "",
    summary="List voice providers for configuration",
    response_model=list[VoiceProviderResponse],
)
async def admin_list_voice_providers(
    _: Any = Depends(require_permission("voice")),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in server.services.voice_provider_repo.list_all()]


@admin_router.post(
    "", status_code=201, summary="Add a voice provider", response_model=VoiceProviderResponse
)
async def admin_create_voice_provider(
    body: VoiceProviderCreateBody,
    _: Any = Depends(require_permission("voice")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    repo = server.services.voice_provider_repo
    _voice_manager(server).validate_configuration(name=body.name, kind=body.kind)
    if repo.get_by_name(body.name):
        raise OctopError(
            ErrorCode.PROVIDER_NAME_TAKEN, f"voice provider {body.name!r} already exists"
        )
    pid = repo.create(
        name=body.name,
        kind=body.kind,
        capability=body.capability,
        base_url=body.base_url,
        api_key=body.api_key,
        extra_json=body.extra_json,
        note=body.note,
    )
    created = repo.get(pid)
    assert created is not None
    return _row_to_dict(created)


@admin_router.patch(
    "/{provider_id}", summary="Update a voice provider", response_model=VoiceProviderResponse
)
async def admin_patch_voice_provider(
    provider_id: int,
    body: VoiceProviderPatchBody,
    _: Any = Depends(require_permission("voice")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    repo = server.services.voice_provider_repo
    row = repo.get(provider_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "voice provider not found")
    _voice_manager(server).validate_update(
        name=row.name,
        kind=body.kind or row.kind,
        capability=body.capability or row.capability,
        enabled=bool(row.enabled) if body.enabled is None else body.enabled,
    )
    repo.update(
        provider_id,
        kind=body.kind,
        capability=body.capability,
        base_url=body.base_url,
        api_key=body.api_key,
        extra_json=body.extra_json,
        note=body.note,
        enabled=body.enabled,
    )
    updated = repo.get(provider_id)
    assert updated is not None
    return _row_to_dict(updated)


@admin_router.delete("/{provider_id}", status_code=204)
async def admin_delete_voice_provider(
    provider_id: int,
    _: Any = Depends(require_permission("voice")),
    server: Any = Depends(get_server),
) -> None:
    repo = server.services.voice_provider_repo
    row = repo.get(provider_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "voice provider not found")
    active = _voice_manager(server).get_active()
    if row.name in {active["stt"], active["tts"]}:
        raise OctopError(
            ErrorCode.PROVIDER_REFERENCED,
            f"voice provider {row.name!r} is currently active",
        )
    repo.delete(provider_id)


@admin_router.post("/{provider_id}/test")
async def admin_test_voice_provider(
    provider_id: int,
    body: VoiceTestBody,
    request: Request,
    _: Any = Depends(require_permission("voice")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return await _voice_manager(server).test_provider(
        provider_id, mode=body.mode, locale=resolve_request_locale(request)
    )


@admin_router.post("/test-configuration", summary="Test an unsaved voice provider configuration")
async def admin_test_voice_configuration(
    body: VoiceConfigurationTestBody,
    request: Request,
    _: Any = Depends(require_permission("voice")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return await _voice_manager(server).test_configuration(
        name=body.name,
        kind=body.kind,
        capability=body.capability,
        base_url=body.base_url,
        api_key=body.api_key,
        extra_json=body.extra_json,
        mode=body.mode,
        locale=resolve_request_locale(request),
    )
