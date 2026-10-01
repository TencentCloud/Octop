"""tests/integration/test_admin_providers.py — admin /api/admin/providers CRUD."""

from __future__ import annotations

import json

import pytest

from octop.infra.agents.providers.probe import _probe_model_id


async def test_provider_probe_model_round_trip_preserves_models_and_headers(env):
    c, srv, auth = env
    models = [
        {"id": "disabled-first", "enabled": False},
        {"id": "enabled-second", "enabled": True},
        {"id": "chosen-third", "enabled": True},
    ]
    response = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={
            "name": "probe-default",
            "kind": "openai",
            "models": models,
            "extra_json": json.dumps({"headers": {"X-Test": "kept"}}),
            "model": "chosen-third",
        },
    )
    assert response.status_code == 201
    provider_id = response.json()["id"]
    assert response.json()["model"] == "chosen-third"
    row = srv.services.provider_repo.get(provider_id)
    assert row.get_models() == models
    assert json.loads(row.extra_json)["headers"] == {"X-Test": "kept"}
    assert _probe_model_id(row, None) == "chosen-third"
    assert _probe_model_id(row, "explicit") == "explicit"

    response = await c.patch(
        f"/api/admin/providers/{provider_id}", headers=auth, json={"model": "enabled-second"}
    )
    assert response.status_code == 200
    listed = (await c.get("/api/admin/providers", headers=auth)).json()
    assert next(item for item in listed if item["id"] == provider_id)["model"] == "enabled-second"
    row = srv.services.provider_repo.get(provider_id)
    assert row.get_models() == models
    assert json.loads(row.extra_json)["headers"] == {"X-Test": "kept"}

    response = await c.patch(
        f"/api/admin/providers/{provider_id}", headers=auth, json={"model": None}
    )
    assert response.status_code == 200
    assert response.json()["model"] is None
    assert _probe_model_id(srv.services.provider_repo.get(provider_id), None) == "enabled-second"


@pytest.mark.parametrize("reset_value", [None, ""])
async def test_provider_probe_model_omission_and_reset_without_other_options(env, reset_value):
    c, srv, auth = env
    created = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "probe-reset", "kind": "openai", "model": "chosen"},
    )
    provider_id = created.json()["id"]
    patched = await c.patch(
        f"/api/admin/providers/{provider_id}", headers=auth, json={"note": "updated"}
    )
    assert patched.json()["model"] == "chosen"
    cleared = await c.patch(
        f"/api/admin/providers/{provider_id}", headers=auth, json={"model": reset_value}
    )
    assert cleared.status_code == 200
    assert cleared.json()["model"] is None
    assert json.loads(srv.services.provider_repo.get(provider_id).extra_json) == {}


async def test_admin_create_and_list(env):
    c, _, auth = env
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "shared-gpt", "kind": "openai", "api_key": "sk-test"},
    )
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == "shared-gpt"
    assert "user_id" not in created

    r = await c.get("/api/admin/providers", headers=auth)
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "shared-gpt" in names


async def test_admin_only_admin_can_create(env):
    c, _, admin_auth = env
    await c.post(
        "/api/users",
        headers=admin_auth,
        json={"username": "regular", "password": "TestPass12", "role": "user"},
    )
    tok = (
        await c.post("/api/auth/login", json={"username": "regular", "password": "TestPass12"})
    ).json()["access_token"]
    user_auth = {"Authorization": f"Bearer {tok}"}

    r = await c.post(
        "/api/admin/providers",
        headers=user_auth,
        json={"name": "should-fail", "kind": "openai"},
    )
    assert r.status_code == 403


async def test_admin_delete(env):
    c, _, auth = env
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "to-delete", "kind": "openai"},
    )
    assert r.status_code == 201
    pid = r.json()["id"]

    r = await c.delete(f"/api/admin/providers/{pid}", headers=auth)
    assert r.status_code in (200, 204)

    r = await c.get("/api/admin/providers", headers=auth)
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert pid not in ids
