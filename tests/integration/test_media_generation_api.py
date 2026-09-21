"""Integration tests for the admin media-generation settings API."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


def _provider_body(*, api_key: str | None = None) -> dict[str, object]:
    return {
        "id": "ark-main",
        "provider": "volcengine",
        "display_name": "Ark Main",
        "enabled": True,
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "image_enabled": True,
        "video_enabled": False,
        "image_model": "seedream-test",
        "video_model": "seedance-test",
        "api_key": api_key,
    }


@pytest.mark.asyncio
async def test_media_generation_keys_are_write_only_and_enable_runtime(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    client, auth = env_admin_client

    initial = await client.get("/api/admin/media-generation", headers=auth)
    assert initial.status_code == 200, initial.text
    assert initial.json()["providers"][0]["api_key_set"] is False

    saved = await client.put(
        "/api/admin/media-generation",
        headers=auth,
        json={
            "enabled": True,
            "providers": [_provider_body(api_key="ark-write-only-test")],
            "default_image_provider": "ark-main",
            "default_video_provider": None,
        },
    )

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["configured"] is True
    assert body["providers"][0]["api_key_set"] is True
    assert "api_key" not in body["providers"][0]
    assert "ark-write-only-test" not in saved.text


@pytest.mark.asyncio
async def test_media_generation_model_test_dispatches_provider_configuration(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    client, auth = env_admin_client
    provider = _provider_body(api_key="ark-draft-test")

    with patch(
        "octop.infra.agents.media_generation.MediaGenerationSettingsStore.test_model",
        new=AsyncMock(return_value={"ok": True}),
    ) as test_model:
        response = await client.post(
            "/api/admin/media-generation/test",
            headers=auth,
            json={"kind": "image", "provider": provider},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "error": None}
    call = test_model.await_args
    assert call.kwargs == {"kind": "image"}
    assert call.args[0].id == "ark-main"
    assert call.args[0].provider == "volcengine"
    assert call.args[0].image_model == "seedream-test"
    assert call.args[0].api_key == "ark-draft-test"


@pytest.mark.asyncio
async def test_media_provider_presets_include_all_p0_adapters(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    client, auth = env_admin_client

    response = await client.get("/api/admin/media-generation/presets", headers=auth)

    assert response.status_code == 200, response.text
    assert [item["provider"] for item in response.json()] == [
        "volcengine",
        "dashscope",
        "minimax",
    ]
    presets = {item["provider"]: item for item in response.json()}
    assert "doubao-seedream-5-0-pro-260628" in presets["volcengine"]["image_models"]
    assert "doubao-seedance-2-5-260628" in presets["volcengine"]["video_models"]
    assert "wan2.7-image-pro" in presets["dashscope"]["image_models"]
    assert "qwen-image-3.0-pro" in presets["dashscope"]["image_models"]
    assert "wan3.0-video-prime" in presets["dashscope"]["video_models"]
    assert "image-01-live" in presets["minimax"]["image_models"]
