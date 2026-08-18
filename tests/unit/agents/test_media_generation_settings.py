"""Tests for encrypted media-generation settings."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from octop.infra.agents.media_generation import (
    MediaGenerationSettingsStore,
    verify_ark_api_key,
    verify_ark_media_model,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo


@pytest.fixture
def store(tmp_path: Path) -> tuple[MediaGenerationSettingsStore, SecretRepo]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    secrets = SecretRepo(db)
    return (
        MediaGenerationSettingsStore(
            settings_repo=SettingsRepo(db),
            secret_repo=secrets,
        ),
        secrets,
    )


def test_media_generation_settings_encrypt_key_and_build_harness_config(
    store: tuple[MediaGenerationSettingsStore, SecretRepo],
) -> None:
    settings, secrets = store
    view = settings.save(
        enabled=True,
        image_enabled=True,
        video_enabled=False,
        image_model="seedream-test",
        video_model="",
        api_key="ark-secret-test",
    )

    assert view.configured is True
    assert view.api_key_set is True
    assert settings.api_key() == "ark-secret-test"
    raw = secrets.get("media_generation_credentials")
    assert raw is not None
    assert b"ark-secret-test" not in raw

    config = settings.harness_config()
    assert config is not None
    assert config.image_enabled is True
    assert config.video_enabled is False
    assert config.resolve_api_key() == "ark-secret-test"


def test_disabled_media_generation_does_not_build_harness_config(
    store: tuple[MediaGenerationSettingsStore, SecretRepo],
) -> None:
    settings, _ = store
    settings.save(
        enabled=False,
        image_enabled=True,
        video_enabled=True,
        image_model="seedream-test",
        video_model="seedance-test",
    )

    assert settings.harness_config() is None


@pytest.mark.asyncio
async def test_verify_ark_api_key_uses_origin_ping() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, text="pong")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await verify_ark_api_key(
            "ark-test",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            client=client,
        )

    assert result == {"ok": True}
    assert seen == {
        "url": "https://ark.cn-beijing.volces.com/ping",
        "auth": "Bearer ark-test",
    }


@pytest.mark.asyncio
async def test_verify_ark_image_model_runs_real_generation_probe() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"data": [{"url": "https://example.com/test.png"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await verify_ark_media_model(
            "ark-test",
            kind="image",
            model="seedream-test",
            client=client,
        )

    assert result == {"ok": True}
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v3/images/generations"
    assert '"model":"seedream-test"' in str(seen["body"])
    assert '"size":"2K"' in str(seen["body"])


@pytest.mark.asyncio
async def test_verify_ark_video_model_cancels_accepted_task() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(200, json={"id": "video-test-task"})
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await verify_ark_media_model(
            "ark-test",
            kind="video",
            model="seedance-test",
            client=client,
        )

    assert result == {"ok": True}
    assert seen == [
        ("POST", "/api/v3/contents/generations/tasks"),
        ("DELETE", "/api/v3/contents/generations/tasks/video-test-task"),
    ]
