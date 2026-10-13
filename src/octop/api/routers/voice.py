"""Voice STT/TTS router."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketState

from octop.api.deps import (
    current_user,
    get_server,
    require_permission,
    resolve_user_from_token,
)
from octop.i18n.domains.voice import realtime_error_message
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.locale import Locale, normalize_locale, resolve_request_locale
from octop.infra.voice import realtime
from octop.infra.voice.manager import VoiceManager
from octop.infra.voice.presets import load_voice_presets

router = APIRouter()
admin_router = APIRouter()


def _voice_manager(server: Any) -> VoiceManager:
    return VoiceManager(
        settings_repo=server.services.settings_repo,
        voice_provider_repo=server.services.voice_provider_repo,
    )


def _active_payload(mgr: VoiceManager) -> dict[str, Any]:
    """Active provider names plus whether STT can stream.

    The dashboard needs ``stt_realtime`` synchronously inside a user gesture to
    decide between streaming and the one-shot upload path.
    """
    active: dict[str, Any] = dict(mgr.get_active())
    active["stt_realtime"] = mgr.realtime_stt_config() is not None
    return active


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


class VoiceProviderCreateBody(BaseModel):
    name: str
    kind: str
    capability: str
    base_url: str | None = None
    api_key: str | None = None
    extra_json: str | None = None
    note: str | None = None


class VoiceProviderPatchBody(BaseModel):
    kind: str | None = None
    capability: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    extra_json: str | None = None
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


@router.get("/presets")
async def list_voice_presets(_: Any = Depends(current_user)) -> list[dict[str, Any]]:
    return load_voice_presets()


@router.get("/providers")
async def list_voice_providers(
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in server.services.voice_provider_repo.list_all()]


@router.get("/active")
async def get_active_voice(
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return _active_payload(_voice_manager(server))


@router.put("/active")
async def set_active_voice(
    body: ActiveVoiceBody,
    _: Any = Depends(require_permission("voice")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    mgr = _voice_manager(server)
    mgr.set_active(stt=body.stt, tts=body.tts)
    return _active_payload(mgr)


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

    # Mimo streams a live WAV (24kHz PCM16LE); other providers stream MP3.
    return StreamingResponse(_stream(), media_type=mgr.media_type(body.provider))


async def _ws_send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
    if websocket.application_state != WebSocketState.CONNECTED:
        return
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        await websocket.send_text(json.dumps(payload, ensure_ascii=False))


async def _ws_error(
    websocket: WebSocket,
    code: ErrorCode,
    locale: Locale,
    *,
    tencent_code: int | None = None,
) -> None:
    message = (
        realtime_error_message(tencent_code, locale)
        if tencent_code is not None
        else OctopError(code, "").localized_message(locale)
    )
    await _ws_send_json(
        websocket,
        {
            "type": "error",
            "code": code.value,
            "message": message,
            "tencent_code": tencent_code,
        },
    )


def _is_end_frame(raw: str) -> bool:
    try:
        control = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return isinstance(control, dict) and control.get("type") == "end"


async def _pump_events(
    session: realtime.TencentRealtimeSession, websocket: WebSocket, locale: Locale
) -> None:
    """Forward upstream recognition events to the browser until the stream ends."""
    async for event in session.events():
        if event.kind == "error":
            await _ws_error(
                websocket,
                ErrorCode.VOICE_REALTIME_UNAVAILABLE,
                locale,
                tencent_code=event.error_code,
            )
            await _ws_send_json(websocket, {"type": "done"})
            return

        if event.kind == "done":
            await _ws_send_json(websocket, {"type": "done"})
            return

        await _ws_send_json(
            websocket,
            {
                "type": event.kind,
                "text": event.text,
                "sentence_id": event.sentence_id,
            },
        )


@router.websocket("/stt-stream")
async def stream_transcription(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    locale: str | None = Query(default=None),
) -> None:
    """Proxy one realtime ASR session to Tencent Cloud over WebSocket.

    The browser sends 16 kHz PCM16 mono frames as binary messages and
    ``{"type": "end"}`` when it is done; the server replies with ``ready`` /
    ``interim`` / ``final`` / ``done`` / ``error`` JSON messages.
    """
    server = websocket.app.state.octop_server
    if not token:
        await websocket.close(code=4001, reason="missing token")
        return
    try:
        resolve_user_from_token(server, token)
    except OctopError as exc:
        await websocket.close(code=4001, reason=f"auth failed: {exc.code.value}")
        return

    await websocket.accept()
    lang = normalize_locale(locale) if locale else resolve_request_locale(websocket)

    config = _voice_manager(server).realtime_stt_config()
    if config is None:
        await _ws_error(websocket, ErrorCode.VOICE_REALTIME_UNAVAILABLE, lang)
        await websocket.close(code=4004, reason="realtime STT is not configured")
        return

    session = realtime.open_session(config)
    reader: asyncio.Task[None] | None = None
    try:
        try:
            await session.connect()
        except OctopError as exc:
            tencent_code = exc.details.get("tencent_code")
            await _ws_error(
                websocket,
                exc.code,
                lang,
                tencent_code=tencent_code if isinstance(tencent_code, int) else None,
            )
            await websocket.close(code=4004, reason="upstream connect failed")
            return

        await _ws_send_json(websocket, {"type": "ready"})
        reader = asyncio.create_task(_pump_events(session, websocket, lang))

        while websocket.application_state == WebSocketState.CONNECTED:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            chunk = message.get("bytes")
            if chunk is not None:
                await session.send_audio(chunk)
                continue
            raw = message.get("text")
            if raw and _is_end_frame(raw):
                await session.finish()
                break

        if reader is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(reader, timeout=realtime.READER_TIMEOUT_SECONDS)
    except WebSocketDisconnect:
        pass
    finally:
        if reader is not None and not reader.done():
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader
        await session.close()
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                await websocket.close()


@admin_router.get("")
async def admin_list_voice_providers(
    _: Any = Depends(require_permission("voice")),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in server.services.voice_provider_repo.list_all()]


@admin_router.post("", status_code=201)
async def admin_create_voice_provider(
    body: VoiceProviderCreateBody,
    _: Any = Depends(require_permission("voice")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    repo = server.services.voice_provider_repo
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


@admin_router.patch("/{provider_id}")
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


@admin_router.post("/test-configuration")
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
