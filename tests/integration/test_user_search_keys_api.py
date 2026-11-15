"""tests/integration/test_user_search_keys_api.py — per-user search keys."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
async def env(env_admin_alice: Any) -> Any:
    yield env_admin_alice


def _row(rows: list[dict[str, Any]], provider_id: str) -> dict[str, Any]:
    return next(item for item in rows if item["provider_id"] == provider_id)


async def test_personal_search_key_round_trip_is_write_only_and_per_user(env: Any) -> None:
    c, srv, admin_auth, alice_auth = env

    r = await c.get("/api/me/search-keys", headers=alice_auth)
    assert r.status_code == 200
    rows = r.json()
    ids = {item["provider_id"] for item in rows}
    assert {"tavily", "brave", "deepseek", "google", "kimi", "yuanbao", "you"} <= ids
    assert all(not item["has_own_key"] for item in rows)
    assert "searchfree" in ids
    assert _row(rows, "searchfree")["personal_key"] is False

    r = await c.put(
        "/api/me/search-keys/deepseek",
        headers=alice_auth,
        json={"env": {"DEEPSEEK_API_KEY": "sk-alice"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["has_own_key"] is True
    assert isinstance(body["updated_at"], int)
    assert "sk-alice" not in r.text

    r = await c.get("/api/me/search-keys", headers=alice_auth)
    assert "sk-alice" not in r.text
    assert _row(r.json(), "deepseek")["has_own_key"] is True

    # Another user's list is unaffected — keys are strictly per user.
    r = await c.get("/api/me/search-keys", headers=admin_auth)
    assert _row(r.json(), "deepseek")["has_own_key"] is False

    r = await c.delete("/api/me/search-keys/deepseek", headers=alice_auth)
    assert r.status_code == 204
    r = await c.get("/api/me/search-keys", headers=alice_auth)
    assert _row(r.json(), "deepseek")["has_own_key"] is False

    actions = {row.action for row in srv.services.audit_repo.query(action="user.search_key_set")}
    assert "user.search_key_set" in actions
    deletes = {row.action for row in srv.services.audit_repo.query(action="user.search_key_delete")}
    assert "user.search_key_delete" in deletes


async def test_google_requires_the_whole_env_set(env: Any) -> None:
    c, _srv, _admin_auth, alice_auth = env

    r = await c.put(
        "/api/me/search-keys/google",
        headers=alice_auth,
        json={"env": {"GOOGLE_API_KEY": "key"}},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"
    listed = await c.get("/api/me/search-keys", headers=alice_auth)
    assert _row(listed.json(), "google")["has_own_key"] is False

    r = await c.put(
        "/api/me/search-keys/google",
        headers=alice_auth,
        json={"env": {"GOOGLE_API_KEY": "key", "GOOGLE_CSE_ID": "cse"}},
    )
    assert r.status_code == 200
    assert r.json()["has_own_key"] is True


async def test_invalid_provider_and_env_are_rejected(env: Any) -> None:
    c, _srv, _admin_auth, alice_auth = env

    r = await c.put(
        "/api/me/search-keys/nope",
        headers=alice_auth,
        json={"env": {"DEEPSEEK_API_KEY": "sk"}},
    )
    assert r.status_code == 404

    r = await c.put(
        "/api/me/search-keys/searchfree",
        headers=alice_auth,
        json={"env": {}},
    )
    assert r.status_code == 404

    r = await c.put(
        "/api/me/search-keys/deepseek",
        headers=alice_auth,
        json={"env": {"DEEPSEEK_API_KEY": "   "}},
    )
    assert r.status_code == 400

    r = await c.put(
        "/api/me/search-keys/deepseek",
        headers=alice_auth,
        json={"env": {"DEEPSEEK_API_KEY": "sk", "UNRELATED": "x"}},
    )
    assert r.status_code == 400

    r = await c.put(
        "/api/me/search-keys/deepseek",
        headers=alice_auth,
        json={"env": {"DEEPSEEK_API_KEY": "sk", "endpoint": "https://evil"}},
    )
    assert r.status_code == 400


async def test_you_accepts_its_optional_key(env: Any) -> None:
    c, _srv, _admin_auth, alice_auth = env
    r = await c.put(
        "/api/me/search-keys/you",
        headers=alice_auth,
        json={"env": {"YDC_API_KEY": "ydc-alice"}},
    )
    assert r.status_code == 200
    assert r.json()["has_own_key"] is True


async def test_user_key_required_follows_missing_global_key(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, _srv, _admin_auth, alice_auth = env

    monkeypatch.setenv("DEEPSEEK_API_KEY", "global")
    r = await c.get("/api/me/search-keys", headers=alice_auth)
    assert _row(r.json(), "deepseek")["user_key_required"] is False

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    r = await c.get("/api/me/search-keys", headers=alice_auth)
    assert _row(r.json(), "deepseek")["user_key_required"] is True


async def test_test_endpoint_uses_stored_or_supplied_values(env: Any) -> None:
    c, _srv, _admin_auth, alice_auth = env
    ok = {"success": True, "result_count": 1, "message": "ok"}

    with patch(
        "octop.api.routers.user_search_keys.probe_search_provider",
        new=AsyncMock(return_value=ok),
    ) as probe:
        r = await c.post("/api/me/search-keys/deepseek/test", headers=alice_auth, json={})
    assert r.status_code == 400

    await c.put(
        "/api/me/search-keys/deepseek",
        headers=alice_auth,
        json={"env": {"DEEPSEEK_API_KEY": "sk-stored"}},
    )
    with patch(
        "octop.api.routers.user_search_keys.probe_search_provider",
        new=AsyncMock(return_value=ok),
    ) as probe:
        r = await c.post("/api/me/search-keys/deepseek/test", headers=alice_auth, json={})
        assert r.status_code == 200
        assert probe.await_args.args[1] == {"DEEPSEEK_API_KEY": "sk-stored"}

    with patch(
        "octop.api.routers.user_search_keys.probe_search_provider",
        new=AsyncMock(return_value=ok),
    ) as probe:
        r = await c.post(
            "/api/me/search-keys/deepseek/test",
            headers=alice_auth,
            json={"env": {"DEEPSEEK_API_KEY": "sk-draft"}},
        )
        assert r.status_code == 200
        assert probe.await_args.args[1] == {"DEEPSEEK_API_KEY": "sk-draft"}


async def test_self_service_requires_auth(env: Any) -> None:
    c, _srv, _admin_auth, _alice_auth = env
    r = await c.get("/api/me/search-keys")
    assert r.status_code == 401


async def test_turn_carries_personal_search_key_to_harness(tmp_octop_home: Any) -> None:
    from tests.support.app import octop_client
    from tests.support.auth import (
        auth_header,
        bootstrap_admin,
        create_agent,
        seed_openai_provider,
    )
    from tests.support.http import chat_ws_path, ws_connect

    async with octop_client(tmp_octop_home) as (client, server):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        await seed_openai_provider(client, auth)
        agent_id = await create_agent(client, auth)
        r = await client.put(
            "/api/me/search-keys/deepseek",
            headers=auth,
            json={"env": {"DEEPSEEK_API_KEY": "sk-personal"}},
        )
        r.raise_for_status()
        created = await client.post(f"/api/agents/{agent_id}/threads", headers=auth)
        thread_id = created.json()["thread_id"]
        async with ws_connect(client._octop_app, chat_ws_path(agent_id, auth)) as ws:
            await ws.send_json({"type": "user_turn", "text": "hi", "thread_id": thread_id})
            frames = await ws.drain_turn()
        assert not any(frame.get("type") == "error" for frame in frames)
        agent = server.app_runtime.agent_registry.get_agent(agent_id)
        assert agent.last_request is not None
        assert agent.last_request["configurable"]["tool_env"] == {"DEEPSEEK_API_KEY": "sk-personal"}
