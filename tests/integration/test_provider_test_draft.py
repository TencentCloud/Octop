"""Integration tests for admin provider test-draft endpoint."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch


async def test_admin_test_draft_requires_api_key(env: Any) -> None:
    client, _srv, auth = env
    r = await client.post(
        "/api/admin/providers/test-draft",
        headers=auth,
        json={
            "name": "draft",
            "kind": "openai",
            "api_key": "",
            "base_url": "https://api.example.com/v1",
            "model_id": "gpt-4o-mini",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False


async def test_admin_test_draft_requires_model_id(env: Any) -> None:
    client, _srv, auth = env
    r = await client.post(
        "/api/admin/providers/test-draft",
        headers=auth,
        json={
            "name": "draft",
            "kind": "openai",
            "api_key": "sk-test",
            "base_url": "https://api.example.com/v1",
            "model_id": "",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False


async def test_admin_codex_oauth_start(env: Any) -> None:
    client, _srv, auth = env
    fake_info = {
        "device_auth_id": "dev-1",
        "user_code": "ABCD-1234",
        "verification_url": "https://auth.openai.com/codex/device",
        "interval_s": 5.0,
    }
    with (
        patch(
            "octop.api.routers.providers.request_device_code",
            return_value=fake_info,
        ),
        patch(
            "octop.api.routers.providers._run_codex_device_poll",
            new=AsyncMock(return_value=None),
        ),
    ):
        r = await client.post(
            "/api/admin/providers/codex-oauth/start",
            headers=auth,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state_id"]
    assert body["user_code"] == "ABCD-1234"
    assert "auth.openai.com" in body["verification_url"]
