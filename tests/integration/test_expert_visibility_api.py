"""tests/integration/test_expert_visibility_api.py — admin-configurable expert visibility.

Covers GET/PUT /api/settings/expert-visibility plus the enforcement on the
built-in expert library and the SkillHub market endpoints (#719):
admins always see everything, non-admin users lose the hidden surfaces, and an
unset policy keeps the historic (fully visible) behaviour.
"""

from __future__ import annotations

from typing import Any

from tests.support.auth import create_user


async def test_defaults_and_read_access_for_any_user(env: Any) -> None:
    c, _srv, admin_auth = env
    user_auth = await create_user(c, admin_auth, username="vis-reader")

    for auth in (admin_auth, user_auth):
        r = await c.get("/api/settings/expert-visibility", headers=auth)
        assert r.status_code == 200, r.text
        assert r.json() == {"hide_builtin_experts": False, "hide_market": False}


async def test_unset_policy_keeps_builtin_visible_for_non_admin(env: Any) -> None:
    c, _srv, admin_auth = env
    user_auth = await create_user(c, admin_auth, username="vis-default")
    r = await c.get("/api/experts", headers=user_auth)
    assert r.status_code == 200, r.text
    assert len(r.json()) >= 1


async def test_put_requires_admin(env: Any) -> None:
    c, _srv, admin_auth = env
    user_auth = await create_user(c, admin_auth, username="vis-putter")
    r = await c.put(
        "/api/settings/expert-visibility",
        headers=user_auth,
        json={"hide_builtin_experts": True, "hide_market": True},
    )
    assert r.status_code == 403, r.text
    # Policy unchanged.
    after = await c.get("/api/settings/expert-visibility", headers=admin_auth)
    assert after.json() == {"hide_builtin_experts": False, "hide_market": False}


async def test_admin_put_roundtrip(env: Any) -> None:
    c, _srv, admin_auth = env
    put = await c.put(
        "/api/settings/expert-visibility",
        headers=admin_auth,
        json={"hide_builtin_experts": True, "hide_market": False},
    )
    assert put.status_code == 200, put.text
    assert put.json() == {"hide_builtin_experts": True, "hide_market": False}

    got = await c.get("/api/settings/expert-visibility", headers=admin_auth)
    assert got.json() == {"hide_builtin_experts": True, "hide_market": False}


async def test_hidden_builtin_filters_listing_for_user_not_admin(env: Any) -> None:
    c, _srv, admin_auth = env
    user_auth = await create_user(c, admin_auth, username="vis-hidden")
    await c.put(
        "/api/settings/expert-visibility",
        headers=admin_auth,
        json={"hide_builtin_experts": True, "hide_market": False},
    )

    user_list = await c.get("/api/experts", headers=user_auth)
    assert user_list.status_code == 200, user_list.text
    assert user_list.json() == []

    admin_list = await c.get("/api/experts", headers=admin_auth)
    assert admin_list.status_code == 200, admin_list.text
    assert len(admin_list.json()) >= 1


async def test_hidden_builtin_forbids_detail_and_create_for_user(env: Any) -> None:
    c, _srv, admin_auth = env
    user_auth = await create_user(c, admin_auth, username="vis-detail")
    await c.put(
        "/api/settings/expert-visibility",
        headers=admin_auth,
        json={"hide_builtin_experts": True, "hide_market": False},
    )

    detail = await c.get("/api/experts/default", headers=user_auth)
    assert detail.status_code == 403, detail.text
    assert detail.json()["error"]["code"] == "FORBIDDEN"

    created = await c.post(
        "/api/agents/from-expert/default",
        headers=user_auth,
        json={"name": "should-not-exist"},
    )
    assert created.status_code == 403, created.text

    admin_detail = await c.get("/api/experts/default", headers=admin_auth)
    assert admin_detail.status_code == 200, admin_detail.text
    assert admin_detail.json()["id"] == "default"


async def test_hidden_market_short_circuits_hub_for_user(env: Any) -> None:
    """Hidden market returns an empty listing / 403 detail without touching SkillHub."""
    c, _srv, admin_auth = env
    user_auth = await create_user(c, admin_auth, username="vis-market")
    await c.put(
        "/api/settings/expert-visibility",
        headers=admin_auth,
        json={"hide_builtin_experts": False, "hide_market": True},
    )

    hub = await c.get("/api/experts/hub", headers=user_auth)
    assert hub.status_code == 200, hub.text
    assert hub.json() == {"items": [], "scenes": []}

    detail = await c.get("/api/experts/hub/any-slug", headers=user_auth)
    assert detail.status_code == 403, detail.text
    assert detail.json()["error"]["code"] == "FORBIDDEN"

    install = await c.post(
        "/api/experts/hub/any-slug/install",
        headers=user_auth,
        json={"name": "should-not-exist"},
    )
    assert install.status_code == 403, install.text


async def test_unhiding_restores_visibility_for_user(env: Any) -> None:
    c, _srv, admin_auth = env
    user_auth = await create_user(c, admin_auth, username="vis-restore")
    await c.put(
        "/api/settings/expert-visibility",
        headers=admin_auth,
        json={"hide_builtin_experts": True, "hide_market": True},
    )
    await c.put(
        "/api/settings/expert-visibility",
        headers=admin_auth,
        json={"hide_builtin_experts": False, "hide_market": False},
    )
    r = await c.get("/api/experts", headers=user_auth)
    assert r.status_code == 200, r.text
    assert len(r.json()) >= 1
