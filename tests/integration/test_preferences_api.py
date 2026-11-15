"""tests/integration/test_preferences_api.py"""

from __future__ import annotations

import json

import pytest

from tests.support.auth import create_user


def _insert_provider(
    srv,
    *,
    name: str,
    api_key: str,
    keyless: bool = False,
) -> None:
    """Insert a provider row directly.

    Creating an empty-key provider through the admin API rehydrates harness
    providers, which requires the harness release that allows an empty
    ``api_key``. The preferences endpoint only reads the repo, so a direct row
    keeps this test independent of that pin.
    """
    srv.services.provider_repo.create(
        name=name,
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key=api_key,
        extra_json='{"keyless": true}' if keyless else None,
        models_json=json.dumps([{"id": "m", "name": "M", "enabled": True, "input": ["text"]}]),
    )


@pytest.mark.asyncio
async def test_preferences_preferred_model_rejects_missing_credential(env) -> None:
    client, srv, auth = env
    _insert_provider(srv, name="byok", api_key="")

    r = await client.patch("/api/preferences", headers=auth, json={"preferred_model": "byok/m"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PROVIDER_KEY_REQUIRED"
    saved = await client.get("/api/preferences", headers=auth)
    assert saved.json()["preferred_model"] is None

    # A personal key makes the same preference valid.
    r = await client.put("/api/me/provider-keys/byok", headers=auth, json={"api_key": "sk-user"})
    r.raise_for_status()
    r = await client.patch("/api/preferences", headers=auth, json={"preferred_model": "byok/m"})
    assert r.status_code == 200
    assert r.json()["preferred_model"] == "byok/m"

    # Clearing a preference never needs a credential.
    r = await client.patch("/api/preferences", headers=auth, json={"preferred_model": None})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_preferences_preferred_model_allows_global_and_keyless(env) -> None:
    client, srv, auth = env
    _insert_provider(srv, name="gw", api_key="sk-global")
    _insert_provider(srv, name="localgw", api_key="", keyless=True)

    for ref in ("gw/m", "localgw/m"):
        r = await client.patch("/api/preferences", headers=auth, json={"preferred_model": ref})
        assert r.status_code == 200, r.text
        assert r.json()["preferred_model"] == ref


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
