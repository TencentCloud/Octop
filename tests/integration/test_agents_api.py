"""tests/integration/test_agents_api.py"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
async def env(env_with_provider):
    yield env_with_provider


async def test_create_and_list(env):
    c, _, auth = env
    r = await c.post(
        "/api/agents",
        headers=auth,
        json={
            "name": "bot",
            "config": {"providers": ["openai"], "default_model": "openai:gpt-4o"},
        },
    )
    assert r.status_code == 201
    agent_id = r.json()["id"]

    r = await c.get("/api/agents", headers=auth)
    assert any(a["id"] == agent_id for a in r.json())


async def test_agent_runtime_fields_are_first_class_api_fields(env):
    c, _, auth = env
    r = await c.post(
        "/api/agents",
        headers=auth,
        json={
            "name": "runtime-config",
            "max_iters": 17,
            "max_input_length": 64_000,
            "temperature": 0.4,
            "top_p": 0.9,
            "max_tokens": 2048,
        },
    )
    assert r.status_code == 201
    created = r.json()
    agent_id = created["agent_id"]
    assert created["max_iters"] == 17
    assert created["max_input_length"] == 64_000
    assert created["temperature"] == 0.4
    assert created["top_p"] == 0.9
    assert created["max_tokens"] == 2048
    assert "max_iters" not in created["config"]

    r = await c.patch(
        f"/api/agents/{agent_id}",
        headers=auth,
        json={"max_iters": 23, "temperature": None},
    )
    assert r.status_code == 200
    updated = r.json()
    assert updated["max_iters"] == 23
    assert updated["temperature"] is None
    assert "max_iters" not in updated["config"]
    assert "temperature" not in updated["config"]


async def test_default_model_patch_waits_for_runtime_reload(env, monkeypatch):
    c, server, auth = env
    created = await c.post(
        "/api/agents",
        headers=auth,
        json={"name": "model-wait", "default_model": "openai/gpt-4o"},
    )
    assert created.status_code == 201
    assert created.json()["default_model"] == "openai/gpt-4o"
    agent_id = created.json()["agent_id"]
    registry = server.app_runtime.agent_registry
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_reload(reloading_id: str) -> None:
        assert reloading_id == agent_id
        started.set()
        await release.wait()

    monkeypatch.setattr(registry, "_reload_agent", delayed_reload)
    request = asyncio.create_task(
        c.patch(
            f"/api/agents/{agent_id}",
            headers=auth,
            json={"default_model": None},
        )
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        assert not request.done(), "PATCH returned before the runtime reload finished"
    finally:
        release.set()
        response = await request

    assert response.status_code == 200
    assert response.json()["default_model"] is None


async def test_create_keeps_legacy_runtime_values_from_config(env):
    c, _, auth = env
    r = await c.post(
        "/api/agents",
        headers=auth,
        json={"name": "legacy-runtime-config", "config": {"max_iters": 19}},
    )
    assert r.status_code == 201
    created = r.json()
    assert created["max_iters"] == 19
    assert "max_iters" not in created["config"]


async def test_start_stop(env):
    """Stop unloads harness runtime; start brings it back."""
    c, _, auth = env
    r = await c.post(
        "/api/agents",
        headers=auth,
        json={
            "name": "bot",
            "config": {"providers": ["openai"], "default_model": "openai:gpt-4o"},
        },
    )
    body = r.json()
    agent_id = body["agent_id"]

    r = await c.get(f"/api/agents/{agent_id}/status", headers=auth)
    assert r.json()["state"] == "running"

    r = await c.post(f"/api/agents/{agent_id}/stop", headers=auth)
    assert r.status_code == 204

    r = await c.get(f"/api/agents/{agent_id}/status", headers=auth)
    assert r.json()["state"] == "stopped"

    r = await c.post(f"/api/agents/{agent_id}/start", headers=auth)
    assert r.status_code == 204

    r = await c.get(f"/api/agents/{agent_id}/status", headers=auth)
    assert r.json()["state"] == "running"

    rows = (await c.get("/api/agents", headers=auth)).json()
    assert any(a["agent_id"] == agent_id for a in rows)


async def test_status_endpoint(env):
    c, _, auth = env
    r = await c.post(
        "/api/agents",
        headers=auth,
        json={
            "name": "bot",
            "config": {"providers": ["openai"], "default_model": "openai:gpt-4o"},
        },
    )
    agent_id = r.json()["agent_id"]
    r = await c.get(f"/api/agents/{agent_id}/status", headers=auth)
    assert r.status_code == 200
    assert "state" in r.json()


async def test_icon_and_color_round_trip(env):
    """icon_name and color stored as first-class fields must appear in GET /agents."""
    c, _srv, auth = env
    r = await c.post(
        "/api/agents",
        headers=auth,
        json={
            "name": "icon-test",
            "config": {"icon_name": "zap", "color": "#6366f1"},
        },
    )
    assert r.status_code == 201
    agent_id = r.json()["id"]

    rows = (await c.get("/api/agents", headers=auth)).json()
    agent = next(a for a in rows if a["id"] == agent_id)
    assert agent["icon_name"] == "zap"
    assert agent["color"] == "#6366f1"


async def test_regular_user_can_list_storage_backends(env):
    """Regular authenticated users can GET /api/storage-backends."""
    c, _srv, auth = env
    r = await c.get("/api/storage-backends", headers=auth)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
