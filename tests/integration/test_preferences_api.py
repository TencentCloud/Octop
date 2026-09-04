"""tests/integration/test_preferences_api.py"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_preferences_bookmarks_roundtrip(env) -> None:
    client, _srv, auth = env
    r = await client.get("/api/preferences", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["locale"] in ("zh", "en")
    assert body["remote_browser_bookmarks"] == []

    bookmarks = [
        {"url": "https://cloud.tencent.com", "title": "Tencent Cloud"},
        {"url": "example.com", "title": "Example"},
    ]
    r = await client.patch(
        "/api/preferences",
        headers=auth,
        json={"remote_browser_bookmarks": bookmarks},
    )
    assert r.status_code == 200
    saved = r.json()["remote_browser_bookmarks"]
    assert len(saved) == 2
    assert saved[0]["url"] == "https://cloud.tencent.com"
    assert saved[1]["url"] == "https://example.com"

    r = await client.get("/api/preferences", headers=auth)
    assert r.json()["remote_browser_bookmarks"] == saved


@pytest.mark.asyncio
async def test_preferences_patch_locale_only_still_works(env) -> None:
    client, _srv, auth = env
    r = await client.patch("/api/preferences", headers=auth, json={"locale": "en"})
    assert r.status_code == 200
    assert r.json()["locale"] == "en"


@pytest.mark.asyncio
async def test_preferences_patch_requires_one_field(env) -> None:
    client, _srv, auth = env
    r = await client.patch("/api/preferences", headers=auth, json={})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_preferences_reasoning_defaults_roundtrip(env) -> None:
    client, _srv, auth = env
    payload = {
        "model_reasoning": {
            "token/glm-5": {"mode": "enabled", "effort": "high"},
        }
    }
    r = await client.patch("/api/preferences", headers=auth, json=payload)
    assert r.status_code == 200
    assert r.json()["model_reasoning"] == payload["model_reasoning"]

    fetched = await client.get("/api/preferences", headers=auth)
    assert fetched.json()["model_reasoning"] == payload["model_reasoning"]


@pytest.mark.asyncio
async def test_preferences_timezone_roundtrip(env) -> None:
    client, _srv, auth = env
    payload = {"timezone": "Asia/Shanghai"}
    r = await client.patch("/api/preferences", headers=auth, json=payload)
    assert r.status_code == 200
    assert r.json()["timezone"] == payload["timezone"]

    r = await client.get("/api/preferences", headers=auth)
    assert r.json()["timezone"] == payload["timezone"]

    r = await client.patch("/api/preferences", headers=auth, json={"timezone": None})
    assert r.status_code == 200
    assert "timezone" in r.json()
    assert r.json()["timezone"] is None


@pytest.mark.asyncio
async def test_preferences_timezone_rejects_invalid_value(env) -> None:
    client, _srv, auth = env
    r = await client.patch("/api/preferences", headers=auth, json={"timezone": "BAD_ZONE"})
    assert r.status_code in (400, 422)
