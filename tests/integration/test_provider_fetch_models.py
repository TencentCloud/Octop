"""Integration tests for admin provider fetch-models endpoint."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch


async def test_admin_fetch_models_requires_api_key(env: Any) -> None:
    client, _srv, auth = env
    r = await client.post(
        "/api/admin/providers/fetch-models",
        headers=auth,
        json={
            "kind": "openai",
            "api_key": "",
            "base_url": "https://api.example.com/v1",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "api_key" in body["error"]


async def test_admin_fetch_models_rejects_non_openai_kind(env: Any) -> None:
    client, _srv, auth = env
    r = await client.post(
        "/api/admin/providers/fetch-models",
        headers=auth,
        json={
            "kind": "anthropic",
            "api_key": "sk-test",
            "base_url": "https://api.anthropic.com",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "openai" in body["error"].lower()


async def test_admin_fetch_models_success(env: Any) -> None:
    client, _srv, auth = env
    fake = {
        "ok": True,
        "models": [{"id": "gpt-4o", "name": "gpt-4o"}],
    }
    with patch(
        "octop.api.routers.providers.fetch_openai_compatible_models",
        new=AsyncMock(return_value=fake),
    ) as mocked:
        r = await client.post(
            "/api/admin/providers/fetch-models",
            headers=auth,
            json={
                "kind": "openai",
                "api_key": "sk-test",
                "base_url": "https://api.example.com/v1",
            },
        )
    assert r.status_code == 200, r.text
    assert r.json() == fake
    mocked.assert_awaited_once()
    kwargs = mocked.await_args.kwargs
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["base_url"] == "https://api.example.com/v1"
