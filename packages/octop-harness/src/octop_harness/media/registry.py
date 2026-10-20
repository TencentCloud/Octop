"""Registry and factory for built-in media generation providers."""

from __future__ import annotations

import httpx

from octop_harness.backends.workspace import BackendWorkspace
from octop_harness.config import MediaGenerationConfig, MediaProviderConfig
from octop_harness.media.base import BaseMediaProvider
from octop_harness.media.manager import MediaJobStore, MediaManager
from octop_harness.media.providers.dashscope import DashScopeMediaProvider
from octop_harness.media.providers.minimax import MiniMaxMediaProvider
from octop_harness.media.providers.volcengine import VolcengineMediaProvider

BUILTIN_MEDIA_PROVIDERS: dict[str, type[BaseMediaProvider]] = {
    "volcengine": VolcengineMediaProvider,
    "dashscope": DashScopeMediaProvider,
    "minimax": MiniMaxMediaProvider,
}


def create_media_provider(
    config: MediaGenerationConfig | MediaProviderConfig,
    *,
    client: httpx.AsyncClient | None = None,
) -> BaseMediaProvider:
    """Construct the adapter selected by ``MediaGenerationConfig.provider``."""
    provider_class = BUILTIN_MEDIA_PROVIDERS.get(config.provider)
    if provider_class is None:
        raise ValueError(f"Unsupported media generation provider: {config.provider!r}")
    return provider_class(config, client=client)


def create_media_manager(
    config: MediaGenerationConfig,
    workspace: BackendWorkspace,
    *,
    job_store: MediaJobStore | None = None,
) -> MediaManager:
    """Build the configured providers and deterministic default routes."""
    manager = MediaManager(workspace, output_dir=config.output_dir, job_store=job_store)
    configured = [item for item in config.configured_providers() if item.enabled]
    for item in configured:
        manager.add_provider(
            item.id,
            create_media_provider(item),
            image_enabled=item.image_enabled,
            video_enabled=item.video_enabled,
        )
    image_route = config.default_image_provider or _preferred_route(configured, kind="image")
    video_route = config.default_video_provider or _preferred_route(configured, kind="video")
    if image_route is not None:
        manager.set_default_route("image", image_route)
    if video_route is not None:
        manager.set_default_route("video", video_route)
    return manager


def _preferred_route(configured: list[MediaProviderConfig], *, kind: str) -> str | None:
    capable = [item for item in configured if getattr(item, f"{kind}_enabled")]
    credentialed = next((item for item in capable if item.has_api_key()), None)
    selected = credentialed or next(iter(capable), None)
    return selected.id if selected is not None else None


__all__ = ["BUILTIN_MEDIA_PROVIDERS", "create_media_manager", "create_media_provider"]
