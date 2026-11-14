"""tests/integration/test_user_provider_keys.py — per-user provider API keys."""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.app import octop_client
from tests.support.auth import auth_header, bootstrap_admin, create_agent, seed_openai_provider
from tests.support.http import chat_ws_path, ws_connect


@pytest.fixture
async def env(env_admin_alice: Any) -> Any:
    yield env_admin_alice


async def test_personal_key_round_trip_is_write_only_and_per_user(env) -> None:
    c, _srv, admin_auth, alice_auth = env

    r = await c.get("/api/me/provider-keys", headers=alice_auth)
    assert r.status_code == 200
    rows = r.json()
    assert rows and all(not item["has_own_key"] for item in rows)
    assert "openai" in [item["provider_name"] for item in rows]

    r = await c.put(
        "/api/me/provider-keys/openai", headers=alice_auth, json={"api_key": "sk-alice"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["has_own_key"] is True
    assert isinstance(body["updated_at"], int)
    assert "sk-alice" not in r.text

    r = await c.get("/api/me/provider-keys", headers=alice_auth)
    assert "sk-alice" not in r.text
    row = next(item for item in r.json() if item["provider_name"] == "openai")
    assert row["has_own_key"] is True

    # Another user's list is unaffected — keys are strictly per user.
    r = await c.get("/api/me/provider-keys", headers=admin_auth)
    row = next(item for item in r.json() if item["provider_name"] == "openai")
    assert row["has_own_key"] is False

    r = await c.delete("/api/me/provider-keys/openai", headers=alice_auth)
    assert r.status_code == 204
    r = await c.get("/api/me/provider-keys", headers=alice_auth)
    row = next(item for item in r.json() if item["provider_name"] == "openai")
    assert row["has_own_key"] is False


async def test_unknown_provider_and_blank_key_are_rejected(env) -> None:
    c, _srv, _admin_auth, alice_auth = env

    r = await c.put("/api/me/provider-keys/nope", headers=alice_auth, json={"api_key": "sk"})
    assert r.status_code == 404
    r = await c.delete("/api/me/provider-keys/nope", headers=alice_auth)
    assert r.status_code == 404
    r = await c.put("/api/me/provider-keys/openai", headers=alice_auth, json={"api_key": "   "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"


async def test_user_key_required_follows_missing_global_key(env) -> None:
    c, srv, _admin_auth, alice_auth = env

    r = await c.get("/api/me/provider-keys", headers=alice_auth)
    row = next(item for item in r.json() if item["provider_name"] == "openai")
    assert row["user_key_required"] is False

    # No global key → the provider demands a personal key. Clear it at the repo
    # layer: the admin PATCH path rehydrates harness ProviderConfigs, and the
    # pinned PyPI harness rejects empty keys (only the patched wheel allows
    # them), so going through the API would fail for environmental reasons.
    provider = srv.services.provider_repo.get_by_name("openai")
    assert provider is not None
    srv.services.provider_repo.update(provider.id, api_key=None)

    r = await c.get("/api/me/provider-keys", headers=alice_auth)
    row = next(item for item in r.json() if item["provider_name"] == "openai")
    assert row["user_key_required"] is True


async def test_explicitly_keyless_provider_is_not_required(env) -> None:
    c, srv, _admin_auth, alice_auth = env

    provider = srv.services.provider_repo.get_by_name("openai")
    assert provider is not None
    srv.services.provider_repo.update(
        provider.id,
        api_key=None,
        extra_json='{"keyless": true}',
    )

    r = await c.get("/api/me/provider-keys", headers=alice_auth)
    row = next(item for item in r.json() if item["provider_name"] == "openai")
    assert row["keyless"] is True
    assert row["user_key_required"] is False


async def test_admin_revoke_clears_global_key(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """PATCH ``{"api_key": null}`` must actually clear the stored global key.

    Regression guard: the request used to return 200 while leaving the key
    in place, so "test connection" kept passing after a revoke.
    """

    async def _noop(**_kwargs: Any) -> None:
        return None

    c, srv, admin_auth, _alice_auth = env
    # The rehydrate step builds harness ProviderConfigs, which the PyPI
    # harness rejects for empty keys (patched wheel only); the API/repo
    # behavior under test does not depend on it.
    monkeypatch.setattr(srv.app_runtime.agent_registry, "on_provider_changed", _noop)

    providers = (await c.get("/api/admin/providers", headers=admin_auth)).json()
    row = next(item for item in providers if item["name"] == "openai")
    assert row["api_key"]
    r = await c.patch(
        f"/api/admin/providers/{row['id']}",
        headers=admin_auth,
        json={"api_key": None},
    )
    assert r.status_code == 200
    assert not r.json()["api_key"]

    listed = (await c.get("/api/admin/providers", headers=admin_auth)).json()
    assert not next(item for item in listed if item["name"] == "openai")["api_key"]
    stored = srv.services.provider_repo.get_by_name("openai")
    assert stored is not None
    assert not stored.api_key


async def test_turn_carries_personal_key_to_harness(tmp_octop_home: Any) -> None:
    async with octop_client(tmp_octop_home) as (client, server):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        await seed_openai_provider(client, auth)
        agent_id = await create_agent(client, auth)
        r = await client.put(
            "/api/me/provider-keys/openai", headers=auth, json={"api_key": "sk-alice"}
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
        assert agent.last_request["configurable"]["api_key_override"] == "sk-alice"


async def test_keyless_provider_blocks_turn_without_key(tmp_octop_home: Any) -> None:
    async with octop_client(tmp_octop_home) as (client, server):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        await seed_openai_provider(client, auth)
        agent_id = await create_agent(client, auth)
        # No real global key → the turn must demand a personal key. Store a
        # whitespace key (blank under our own resolution semantics) rather
        # than None at the repo layer: None makes the model ref unresolvable
        # before the keyless-usability PR (feat/model-keyless-usable), so the
        # turn would never reach the personal-key gate this test covers.
        provider = server.services.provider_repo.get_by_name("openai")
        assert provider is not None
        server.services.provider_repo.update(provider.id, api_key="  ")
        created = await client.post(f"/api/agents/{agent_id}/threads", headers=auth)
        thread_id = created.json()["thread_id"]
        async with ws_connect(client._octop_app, chat_ws_path(agent_id, auth)) as ws:
            await ws.send_json({"type": "user_turn", "text": "hi", "thread_id": thread_id})
            frames = await ws.drain_turn()
        error = next((f for f in frames if f.get("type") == "error"), None)
        assert error is not None
        # The frame's ``error_code=PROVIDER_KEY_REQUIRED`` is composed with the
        # stream-error envelope fix (PR-O2 — see
        # tests/unit/gateway/test_processor_resource_errors.py); the code and
        # localized copy are asserted on the OctopError itself in
        # test_user_key_resolution.py, and end-to-end in the deploy checklist.
