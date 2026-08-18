"""Integration tests for the admin media-generation settings API."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_media_generation_key_is_write_only_and_enables_runtime(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    client, auth = env_admin_client

    initial = await client.get("/api/admin/media-generation", headers=auth)
    assert initial.status_code == 200, initial.text
    assert initial.json()["api_key_set"] is False

    with patch(
        "octop.infra.agents.media_generation.verify_ark_api_key",
        new=AsyncMock(return_value={"ok": True}),
    ):
        saved = await client.put(
            "/api/admin/media-generation",
            headers=auth,
            json={
                "enabled": True,
                "image_enabled": True,
                "video_enabled": False,
                "image_model": "seedream-test",
                "video_model": "",
                "api_key": "ark-write-only-test",
            },
        )

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["configured"] is True
    assert body["api_key_set"] is True
    assert "api_key" not in body
    assert "ark-write-only-test" not in saved.text


@pytest.mark.asyncio
async def test_media_generation_model_test_dispatches_selected_model(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    client, auth = env_admin_client

    with patch(
        "octop.infra.agents.media_generation.MediaGenerationSettingsStore.test_model",
        new=AsyncMock(return_value={"ok": True}),
    ) as test_model:
        response = await client.post(
            "/api/admin/media-generation/test",
            headers=auth,
            json={
                "kind": "image",
                "api_key": "ark-draft-test",
                "image_model": "seedream-selected",
            },
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "error": None}
    test_model.assert_awaited_once_with(
        kind="image",
        model="seedream-selected",
        api_key="ark-draft-test",
    )
