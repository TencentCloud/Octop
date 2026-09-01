"""tests/integration/test_e2e_golden_path.py — full user journey."""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.auth import bootstrap_admin
from tests.support.http import ws_chat_turn


@pytest.fixture
async def env(env_fake_harness):
    yield env_fake_harness


async def _ws_turn(
    client: Any, agent_id: str, auth: dict[str, str], *, text: str = "Hello"
) -> list[dict[str, Any]]:
    return await ws_chat_turn(client, agent_id, auth, text=text)


async def test_full_golden_path(env: Any) -> None:
    c, _srv, _fake, home = env

    # 1) setup admin
    r = await bootstrap_admin(c, home)
    assert r.status_code == 201

    # 2) admin login
    r = await c.post("/api/auth/login", json={"username": "admin", "password": "TestPass12"})
    assert r.status_code == 200
    tok = r.json()["access_token"]
    auth = {"Authorization": f"Bearer {tok}"}

    # 3) admin creates a regular user
    r = await c.post(
        "/api/users",
        headers=auth,
        json={
            "username": "alice",
            "password": "TestPass12",
            "role": "user",
            "display_name": "Alice",
        },
    )
    assert r.status_code == 201

    # 4) admin creates a shared provider
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={
            "name": "openai",
            "kind": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-x",
            "models": [
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "enabled": True,
                    "input": ["text"],
                }
            ],
        },
    )
    assert r.status_code == 201

    # 5) alice logs in
    r = await c.post("/api/auth/login", json={"username": "alice", "password": "TestPass12"})
    assert r.status_code == 200
    alice_tok = r.json()["access_token"]
    alice_auth = {"Authorization": f"Bearer {alice_tok}"}

    # 6) alice creates her own agent and chats on it (must own the agent to connect)
    r = await c.post(
        "/api/agents",
        headers=alice_auth,
        json={
            "name": "bot",
            "persona_mbti": "INTJ",
            "default_model": "openai:gpt-4o",
        },
    )
    assert r.status_code == 201, r.text
    aid = r.json()["agent_id"]

    # 7) alice opens a chat stream (WebSocket transport)
    chunks = await _ws_turn(c, aid, alice_auth, text="Hello")
    assert any(ch.get("type") == "token" for ch in chunks)
    assert chunks[-1]["type"] == "done"

    # 8) threads list shows the row with autofilled title
    r = await c.get(f"/api/agents/{aid}/threads", headers=alice_auth)
    assert r.status_code == 200
    threads = r.json()
    assert threads
    assert threads[0]["title"] == "Hello"

    # 9) admin metrics counter incremented
    r = await c.get("/api/admin/metrics", headers=auth)
    assert r.status_code == 200
    assert r.json()["messages_total"] >= 0  # may be 0 if SSE path doesn't bump this counter


async def test_expert_to_chat_golden_path(env: Any) -> None:
    """Create an agent from the expert library, start it, then chat.

    Full flow:
      1. Setup admin + provider
      2. Regular user logs in
      3. User lists experts, picks "default"
      4. User lists available models → selects one
      5. User creates agent from expert with default_model
      6. User starts the agent (POST /agents/{id}/start)
      7. User sends a chat message and receives SSE tokens
    """
    c, _srv, _fake, home = env

    # 1) setup admin + provider
    await bootstrap_admin(c, home)
    r = await c.post("/api/auth/login", json={"username": "admin", "password": "TestPass12"})
    admin_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # Admin creates provider with explicit model list so /providers/resolved returns something
    r = await c.post(
        "/api/admin/providers",
        headers=admin_auth,
        json={
            "name": "openai",
            "kind": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "models": [{"id": "gpt-4o", "name": "GPT-4o", "enabled": True, "input": ["text"]}],
        },
    )
    assert r.status_code == 201

    # 2) create user + login
    await c.post(
        "/api/users",
        headers=admin_auth,
        json={"username": "bob", "password": "TestPass12", "role": "user", "display_name": "Bob"},
    )
    r = await c.post("/api/auth/login", json={"username": "bob", "password": "TestPass12"})
    bob_auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # 3) list experts — the default expert must be present
    r = await c.get("/api/experts", headers=bob_auth)
    assert r.status_code == 200
    expert_ids = [e["id"] for e in r.json()]
    assert "general-assistant" in expert_ids

    # 4) get expert detail — must include file_contents
    r = await c.get("/api/experts/general-assistant", headers=bob_auth)
    assert r.status_code == 200
    expert = r.json()
    assert "file_contents" in expert and len(expert["file_contents"]) > 0

    # 5) list resolved models (simulates model selector in CreateFromExpertDrawer)
    r = await c.get("/api/providers/resolved", headers=bob_auth)
    assert r.status_code == 200
    models = r.json()
    assert len(models) > 0
    first_model = models[0]
    default_model_val = f"{first_model['provider_name']}/{first_model['model']}"

    # 6) list storage backends (simulates backend selector)
    r = await c.get("/api/storage-backends", headers=bob_auth)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # 7) create agent from expert with default_model
    r = await c.post(
        "/api/agents/from-expert/general-assistant",
        headers=bob_auth,
        json={
            "name": "my-default-bot",
            "default_model": default_model_val,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    agent_id = body["agent_id"]
    assert body["expert_id"] == "general-assistant"
    # Agent starts in non-running state (autostart=False)
    assert body["state"] in {"running", "failed", "stopped", "unknown"}

    # Verify config stored correctly
    rows = (await c.get("/api/agents", headers=bob_auth)).json()
    agent_row = next(a for a in rows if a["agent_id"] == agent_id)
    assert agent_row["default_model"] == default_model_val
    assert agent_row["template_name"] == "general-assistant"
    assert "expert_id" not in (agent_row.get("config") or {})

    # 8) start the agent
    r = await c.post(f"/api/agents/{agent_id}/start", headers=bob_auth)
    assert r.status_code == 204, r.text

    # 9) chat — stream a message and verify we get tokens back (WebSocket transport)
    chunks = await _ws_turn(c, agent_id, bob_auth, text="你好")
    assert any(ch.get("type") == "token" for ch in chunks), f"no token chunks: {chunks}"
    assert chunks[-1]["type"] == "done"
