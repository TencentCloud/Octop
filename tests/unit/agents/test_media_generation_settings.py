"""Tests for encrypted multi-provider media-generation settings."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from octop.infra.agents.settings.media_generation import (
    DEFAULT_PROVIDER_ID,
    MediaGenerationSettingsStore,
    MediaProviderUpdate,
    verify_media_credentials,
)
from octop.infra.connectors.crypto import encrypt_credentials
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo


@pytest.fixture
def store(
    tmp_path: Path,
) -> tuple[MediaGenerationSettingsStore, SettingsRepo, SecretRepo]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    settings = SettingsRepo(db)
    secrets = SecretRepo(db)
    return (
        MediaGenerationSettingsStore(
            settings_repo=settings,
            secret_repo=secrets,
        ),
        settings,
        secrets,
    )


def _provider(
    provider_id: str,
    provider: str,
    *,
    api_key: str | None = None,
    image_enabled: bool = True,
    video_enabled: bool = True,
    three_d_enabled: bool = False,
    three_d_model: str | None = None,
) -> MediaProviderUpdate:
    defaults = {
        "volcengine": (
            "https://ark.cn-beijing.volces.com/api/v3",
            "seedream-test",
            "seedance-test",
            "",
        ),
        "dashscope": (
            "https://dashscope.aliyuncs.com/api/v1",
            "wan-image-test",
            "wan-video-test",
            "",
        ),
        "tencent-tokenhub": (
            "https://tokenhub.tencentmaas.com/v1",
            "hy-image-v3.5-preview",
            "hy-video-v1.5",
            "hy-3d-3.6",
        ),
    }
    base_url, image_model, video_model, default_3d = defaults[provider]
    return MediaProviderUpdate(
        id=provider_id,
        provider=provider,  # type: ignore[arg-type]
        display_name=provider_id,
        enabled=True,
        base_url=base_url,
        image_enabled=image_enabled,
        video_enabled=video_enabled,
        three_d_enabled=three_d_enabled,
        image_model=image_model,
        video_model=video_model,
        three_d_model=default_3d if three_d_model is None else three_d_model,
        api_key=api_key,
    )


def test_media_generation_settings_encrypt_keys_and_build_routes(
    store: tuple[MediaGenerationSettingsStore, SettingsRepo, SecretRepo],
) -> None:
    media, settings, secrets = store
    view = media.save(
        enabled=True,
        providers=[
            _provider(
                "ark-image",
                "volcengine",
                api_key="ark-secret-test",
                video_enabled=False,
            ),
            _provider(
                "wan-video",
                "dashscope",
                api_key="dashscope-secret-test",
                image_enabled=False,
            ),
        ],
        default_image_provider="ark-image",
        default_video_provider="wan-video",
    )

    assert view.configured is True
    assert [item.api_key_set for item in view.providers] == [True, True]
    assert media.api_key("ark-image") == "ark-secret-test"
    assert media.api_key("wan-video") == "dashscope-secret-test"
    raw = secrets.get("media_generation_credentials_v2")
    assert raw is not None
    assert b"ark-secret-test" not in raw
    assert b"dashscope-secret-test" not in raw
    assert "secret-test" not in (settings.get("media_generation_config_v2") or "")

    config = media.harness_config()
    assert config is not None
    assert config.default_image_provider == "ark-image"
    assert config.default_video_provider == "wan-video"
    assert [item.id for item in config.providers] == ["ark-image", "wan-video"]
    assert [item.provider for item in config.providers] == ["volcengine", "dashscope"]


def test_legacy_ark_settings_are_exposed_as_default_provider(
    store: tuple[MediaGenerationSettingsStore, SettingsRepo, SecretRepo],
) -> None:
    media, settings, secrets = store
    settings.set("media_generation_enabled", "true")
    settings.set("media_generation_image_enabled", "true")
    settings.set("media_generation_video_enabled", "false")
    settings.set("media_generation_image_model", "legacy-seedream")
    secrets.get_or_create(
        "media_generation_credentials",
        lambda: encrypt_credentials(secrets, {"api_key": "legacy-ark-key"}),
    )

    view = media.load()

    assert view.enabled is True
    assert view.default_image_provider == DEFAULT_PROVIDER_ID
    assert view.default_video_provider is None
    assert len(view.providers) == 1
    assert view.providers[0].provider == "volcengine"
    assert view.providers[0].image_model == "legacy-seedream"
    assert view.providers[0].api_key_set is True
    assert media.api_key(DEFAULT_PROVIDER_ID) == "legacy-ark-key"


def test_disabled_media_generation_does_not_build_harness_config(
    store: tuple[MediaGenerationSettingsStore, SettingsRepo, SecretRepo],
) -> None:
    media, _, _ = store
    media.save(
        enabled=False,
        providers=[_provider("ark-main", "volcengine")],
        default_image_provider="ark-main",
        default_video_provider="ark-main",
    )

    assert media.harness_config() is None


@pytest.mark.parametrize(
    ("provider", "base_url", "expected_url"),
    [
        (
            "volcengine",
            "https://ark.cn-beijing.volces.com/api/v3",
            "https://ark.cn-beijing.volces.com/ping",
        ),
        (
            "dashscope",
            "https://dashscope.aliyuncs.com/api/v1",
            "https://dashscope.aliyuncs.com/api/v1/models?page_no=1&page_size=1",
        ),
        (
            "minimax",
            "https://api.minimax.cn",
            "https://api.minimax.cn/v1/models",
        ),
        (
            "tencent-tokenhub",
            "https://tokenhub.tencentmaas.com/v1",
            "https://tokenhub.tencentmaas.com/v1/models",
        ),
    ],
)
@pytest.mark.asyncio
async def test_verify_media_credentials_uses_provider_probe(
    provider: str,
    base_url: str,
    expected_url: str,
) -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await verify_media_credentials(
            provider,  # type: ignore[arg-type]
            "provider-test-key",
            base_url=base_url,
            client=client,
        )

    assert result == {"ok": True}
    assert seen == {
        "url": expected_url,
        "auth": "Bearer provider-test-key",
    }


def test_tencent_tokenhub_three_d_settings_and_non_3d_rejection(
    store: tuple[MediaGenerationSettingsStore, SettingsRepo, SecretRepo],
) -> None:
    import importlib

    from octop.infra.errors import OctopError

    media, _, _ = store
    with pytest.raises(OctopError, match="does not support 3D generation"):
        media.save(
            enabled=True,
            providers=[
                _provider(
                    "ark-3d",
                    "volcengine",
                    api_key="ark-key",
                    three_d_enabled=True,
                    three_d_model="hy-3d-3.6",
                )
            ],
            default_image_provider="ark-3d",
            default_video_provider="ark-3d",
            default_three_d_provider="ark-3d",
        )

    view = media.save(
        enabled=True,
        providers=[
            _provider(
                "tokenhub-main",
                "tencent-tokenhub",
                api_key="tokenhub-secret-test",
                image_enabled=False,
                video_enabled=False,
                three_d_enabled=True,
            )
        ],
        default_image_provider=None,
        default_video_provider=None,
        default_three_d_provider="tokenhub-main",
    )

    assert view.configured is True
    assert view.default_three_d_provider == "tokenhub-main"
    assert view.providers[0].three_d_enabled is True
    assert view.providers[0].three_d_model == "hy-3d-3.6"
    assert media.api_key("tokenhub-main") == "tokenhub-secret-test"

    media_mod = importlib.import_module("octop_harness.media")
    supported = set(getattr(media_mod, "BUILTIN_MEDIA_PROVIDERS", ()))
    config = media.harness_config()
    if "tencent-tokenhub" in supported:
        assert config is not None
        assert getattr(config, "default_three_d_provider", None) == "tokenhub-main"
        assert config.providers[0].provider == "tencent-tokenhub"
        assert getattr(config.providers[0], "three_d_model", "") == "hy-3d-3.6"
    else:
        assert config is None


@pytest.mark.asyncio
async def test_verify_media_credentials_surfaces_tokenhub_error_envelope() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"code": "1002", "message": "Invalid API key"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await verify_media_credentials(
            "tencent-tokenhub",
            "bad-key",
            base_url="https://tokenhub.tencentmaas.com/v1",
            client=client,
        )

    assert result == {"ok": False, "error": "Invalid API key"}
