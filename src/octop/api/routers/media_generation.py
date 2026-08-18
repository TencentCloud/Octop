"""Admin API for instance-wide image and video generation settings."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.agents.media_generation import (
    DEFAULT_ARK_BASE_URL,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_VIDEO_MODEL,
)
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()


class MediaGenerationSettingsResponse(BaseModel):
    enabled: bool
    provider: str
    base_url: str
    image_enabled: bool
    video_enabled: bool
    image_model: str
    video_model: str
    api_key_set: bool
    configured: bool


class MediaGenerationSettingsBody(BaseModel):
    enabled: bool = False
    image_enabled: bool = True
    video_enabled: bool = True
    image_model: str = DEFAULT_IMAGE_MODEL
    video_model: str = DEFAULT_VIDEO_MODEL
    api_key: str | None = Field(
        default=None,
        description="Write-only Ark inference API key; omit to keep the stored key.",
    )


class MediaGenerationTestBody(BaseModel):
    kind: Literal["credentials", "image", "video"] = "credentials"
    api_key: str | None = Field(
        default=None,
        description="Draft Ark API key; omit to test the stored key.",
    )
    image_model: str = DEFAULT_IMAGE_MODEL
    video_model: str = DEFAULT_VIDEO_MODEL


class MediaGenerationTestResponse(BaseModel):
    ok: bool
    error: str | None = None


def _response(view: Any) -> MediaGenerationSettingsResponse:
    return MediaGenerationSettingsResponse(
        enabled=view.enabled,
        provider=view.provider,
        base_url=view.base_url,
        image_enabled=view.image_enabled,
        video_enabled=view.video_enabled,
        image_model=view.image_model,
        video_model=view.video_model,
        api_key_set=view.api_key_set,
        configured=view.configured,
    )


@router.get(
    "",
    summary="Get media generation settings",
    response_model=MediaGenerationSettingsResponse,
)
async def get_media_generation_settings(
    _: Any = Depends(require_permission("providers")),
    server: Any = Depends(get_server),
) -> MediaGenerationSettingsResponse:
    return _response(server.app_runtime.agent_registry.media_generation.load())


@router.put(
    "",
    summary="Update media generation settings",
    response_model=MediaGenerationSettingsResponse,
)
async def put_media_generation_settings(
    body: MediaGenerationSettingsBody,
    _: Any = Depends(require_permission("providers")),
    server: Any = Depends(get_server),
) -> MediaGenerationSettingsResponse:
    api_key = (body.api_key or "").strip() or None
    store = server.app_runtime.agent_registry.media_generation
    if api_key is not None:
        result = await store.test_connection(api_key=api_key)
        if not result.get("ok"):
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                str(result.get("error") or "Ark API key verification failed"),
            )
    view = await server.app_runtime.agent_registry.save_media_generation(
        enabled=body.enabled,
        image_enabled=body.image_enabled,
        video_enabled=body.video_enabled,
        image_model=body.image_model,
        video_model=body.video_model,
        api_key=api_key,
    )
    return _response(view)


@router.post(
    "/test",
    summary="Test Ark media generation credentials",
    response_model=MediaGenerationTestResponse,
)
async def test_media_generation_credentials(
    body: MediaGenerationTestBody,
    _: Any = Depends(require_permission("providers")),
    server: Any = Depends(get_server),
) -> MediaGenerationTestResponse:
    store = server.app_runtime.agent_registry.media_generation
    api_key = (body.api_key or "").strip() or None
    if body.kind == "credentials":
        result = await store.test_connection(api_key=api_key)
    else:
        result = await store.test_model(
            kind=body.kind,
            model=body.image_model if body.kind == "image" else body.video_model,
            api_key=api_key,
        )
    return MediaGenerationTestResponse(
        ok=bool(result.get("ok")),
        error=str(result["error"]) if result.get("error") else None,
    )


__all__ = ["DEFAULT_ARK_BASE_URL", "router"]
