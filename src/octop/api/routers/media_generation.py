"""Admin API for instance-wide image and video generation settings."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.agents.media_generation import (
    MEDIA_PROVIDER_PRESETS,
    MediaGenerationSettings,
    MediaProviderName,
    MediaProviderSettings,
    MediaProviderUpdate,
)

router = APIRouter()


class MediaProviderPresetResponse(BaseModel):
    provider: MediaProviderName
    display_name: str
    base_url: str
    image_models: list[str]
    video_models: list[str]


class MediaProviderResponse(BaseModel):
    id: str
    provider: MediaProviderName
    display_name: str
    enabled: bool
    base_url: str
    image_enabled: bool
    video_enabled: bool
    image_model: str
    video_model: str
    api_key_set: bool
    configured: bool


class MediaGenerationSettingsResponse(BaseModel):
    enabled: bool
    providers: list[MediaProviderResponse]
    default_image_provider: str | None
    default_video_provider: str | None
    configured: bool


class MediaProviderBody(BaseModel):
    id: str = Field(description="Stable provider-instance routing ID.")
    provider: MediaProviderName
    display_name: str
    enabled: bool = True
    base_url: str
    image_enabled: bool = True
    video_enabled: bool = True
    image_model: str
    video_model: str
    api_key: str | None = Field(
        default=None,
        description="Write-only API key; omit to keep the stored value.",
    )
    clear_api_key: bool = Field(
        default=False,
        description="Delete the stored API key for this provider instance.",
    )

    def to_domain(self) -> MediaProviderUpdate:
        return MediaProviderUpdate(**self.model_dump())


class MediaGenerationSettingsBody(BaseModel):
    enabled: bool = False
    providers: list[MediaProviderBody] = Field(default_factory=list, max_length=8)
    default_image_provider: str | None = None
    default_video_provider: str | None = None


class MediaGenerationTestBody(BaseModel):
    kind: Literal["credentials", "image", "video"] = "credentials"
    provider: MediaProviderBody


class MediaGenerationTestResponse(BaseModel):
    ok: bool
    error: str | None = None


def _provider_response(view: MediaProviderSettings) -> MediaProviderResponse:
    return MediaProviderResponse(
        id=view.id,
        provider=view.provider,
        display_name=view.display_name,
        enabled=view.enabled,
        base_url=view.base_url,
        image_enabled=view.image_enabled,
        video_enabled=view.video_enabled,
        image_model=view.image_model,
        video_model=view.video_model,
        api_key_set=view.api_key_set,
        configured=view.configured,
    )


def _response(view: MediaGenerationSettings) -> MediaGenerationSettingsResponse:
    return MediaGenerationSettingsResponse(
        enabled=view.enabled,
        providers=[_provider_response(item) for item in view.providers],
        default_image_provider=view.default_image_provider,
        default_video_provider=view.default_video_provider,
        configured=view.configured,
    )


@router.get(
    "/presets",
    summary="List built-in media provider presets",
    description="Return supported provider adapters and their default image and video models.",
    response_model=list[MediaProviderPresetResponse],
)
async def list_media_provider_presets(
    _: Any = Depends(require_permission("providers")),
) -> list[MediaProviderPresetResponse]:
    return [
        MediaProviderPresetResponse(
            provider=item.provider,
            display_name=item.display_name,
            base_url=item.base_url,
            image_models=list(item.image_models),
            video_models=list(item.video_models),
        )
        for item in MEDIA_PROVIDER_PRESETS.values()
    ]


@router.get(
    "",
    summary="Get media generation settings",
    description=(
        "Return instance-wide provider instances and default image/video routes. "
        "Stored API keys are never returned."
    ),
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
    description=(
        "Persist provider instances and deterministic default routes, then reload "
        "running agents. API keys are write-only; omit them to retain stored values."
    ),
    response_model=MediaGenerationSettingsResponse,
)
async def put_media_generation_settings(
    body: MediaGenerationSettingsBody,
    _: Any = Depends(require_permission("providers")),
    server: Any = Depends(get_server),
) -> MediaGenerationSettingsResponse:
    view = await server.app_runtime.agent_registry.save_media_generation(
        enabled=body.enabled,
        providers=[item.to_domain() for item in body.providers],
        default_image_provider=body.default_image_provider,
        default_video_provider=body.default_video_provider,
    )
    return _response(view)


@router.post(
    "/test",
    summary="Test a media provider configuration",
    description=(
        "Test credentials without generation, or submit a real image/video model "
        "request. Model tests may incur provider charges."
    ),
    response_model=MediaGenerationTestResponse,
)
async def test_media_generation_provider(
    body: MediaGenerationTestBody,
    _: Any = Depends(require_permission("providers")),
    server: Any = Depends(get_server),
) -> MediaGenerationTestResponse:
    store = server.app_runtime.agent_registry.media_generation
    provider = body.provider.to_domain()
    if body.kind == "credentials":
        result = await store.test_connection(provider)
    else:
        result = await store.test_model(provider, kind=body.kind)
    return MediaGenerationTestResponse(
        ok=bool(result.get("ok")),
        error=str(result["error"]) if result.get("error") else None,
    )


__all__ = ["router"]
