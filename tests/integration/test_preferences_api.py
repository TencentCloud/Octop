"""tests/integration/test_preferences_api.py"""

from __future__ import annotations

import pytest

from tests.support.auth import create_user


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


@pytest.mark.asyncio
async def test_preferences_sidebar_nav_roundtrip(env) -> None:
    client, _srv, auth = env
    r = await client.get("/api/preferences", headers=auth)
    assert r.status_code == 200
    assert r.json()["sidebar_nav"] is None

    payload = {
        "sidebar_nav": {
            "groups": [{"id": "settings"}, {"id": "c_aabbccdd1122", "name": "常用"}],
            "items": [
                {"key": "chat"},
                {"key": "experts", "group": "c_aabbccdd1122"},
                {"key": "tasks", "hidden": True},
            ],
        }
    }
    r = await client.patch("/api/preferences", headers=auth, json=payload)
    assert r.status_code == 200
    saved = r.json()["sidebar_nav"]
    assert saved["groups"][1]["name"] == "常用"
    assert saved["items"][1]["group"] == "c_aabbccdd1122"
    assert saved["items"][2]["key"] == "tasks"
    assert saved["items"][2]["hidden"] is True

    r = await client.patch("/api/preferences", headers=auth, json={"sidebar_nav": None})
    assert r.status_code == 200
    assert r.json()["sidebar_nav"] is None


@pytest.mark.asyncio
async def test_preferences_onboarding_is_per_user(env) -> None:
    client, _srv, admin = env
    member = await create_user(client, admin, username="newcomer")

    for auth in (admin, member):
        r = await client.get("/api/preferences", headers=auth)
        assert r.status_code == 200
        assert r.json()["onboarding_completed"] is False

    r = await client.patch("/api/preferences", headers=member, json={"onboarding_completed": True})
    assert r.status_code == 200
    assert r.json()["onboarding_completed"] is True

    r = await client.get("/api/preferences", headers=member)
    assert r.json()["onboarding_completed"] is True
    r = await client.get("/api/preferences", headers=admin)
    assert r.json()["onboarding_completed"] is False

    r = await client.patch("/api/preferences", headers=member, json={"onboarding_completed": False})
    assert r.status_code == 200
    assert r.json()["onboarding_completed"] is False


@pytest.mark.asyncio
async def test_preferences_onboarding_keeps_other_preferences(env) -> None:
    client, _srv, auth = env
    r = await client.patch("/api/preferences", headers=auth, json={"timezone": "Asia/Shanghai"})
    assert r.status_code == 200

    r = await client.patch("/api/preferences", headers=auth, json={"onboarding_completed": True})
    assert r.status_code == 200
    body = r.json()
    assert body["onboarding_completed"] is True
    assert body["timezone"] == "Asia/Shanghai"
