"""HTTP trajectory history, event detail, metrics, and export (no SSE)."""

from __future__ import annotations

import json
from typing import Any


def _url(agent_id: str, thread_id: str, suffix: str = "") -> str:
    return f"/api/agents/{agent_id}/threads/{thread_id}/trajectory{suffix}"


async def _create_thread(client: Any, auth: dict[str, str], agent_id: str) -> str:
    response = await client.post(f"/api/agents/{agent_id}/threads", headers=auth)
    assert response.status_code == 201, response.text
    return str(response.json()["thread_id"])


async def test_owner_gets_empty_trajectory_list(env_alice_bob_agent: Any) -> None:
    client, _srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)

    response = await client.get(_url(agent_id, thread_id), headers=alice_auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["thread_id"] == thread_id
    assert body["events"] == []
    assert body["has_more"] is False
    assert body.get("next_before_seq") is None


async def test_non_owner_cannot_read_trajectory(env_alice_bob_agent: Any) -> None:
    client, _srv, alice_auth, bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)

    response = await client.get(_url(agent_id, thread_id), headers=bob_auth)
    assert response.status_code in (403, 404)

    response = await client.get(_url(agent_id, thread_id, "/metrics"), headers=bob_auth)
    assert response.status_code in (403, 404)

    response = await client.get(_url(agent_id, thread_id, "/export"), headers=bob_auth)
    assert response.status_code in (403, 404)


async def test_missing_thread_is_not_found(env_alice_bob_agent: Any) -> None:
    client, _srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent

    response = await client.get(_url(agent_id, "no-such-thread"), headers=alice_auth)
    assert response.status_code == 404


async def test_list_returns_summarized_events_after_append(env_alice_bob_agent: Any) -> None:
    client, srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)
    service = srv.app_runtime.trajectory_service
    assert service is not None
    service.observe_chunk(agent_id, thread_id, {"type": "user", "content": "hello there"})

    response = await client.get(_url(agent_id, thread_id), headers=alice_auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["thread_id"] == thread_id
    assert len(body["events"]) == 1
    event = body["events"][0]
    assert event["kind"] == "user"
    assert "hello there" in event["summary"]
    assert event["payload"].get("content") is None

    detail = await client.get(
        _url(agent_id, thread_id, f"/events/{event['event_id']}"),
        headers=alice_auth,
    )
    assert detail.status_code == 200, detail.text
    full = detail.json()
    assert full["event_id"] == event["event_id"]
    assert full["payload"]["content"] == "hello there"


async def test_metrics_and_jsonl_export(env_alice_bob_agent: Any) -> None:
    client, srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)
    service = srv.app_runtime.trajectory_service
    assert service is not None
    service.observe_chunk(agent_id, thread_id, {"type": "user", "content": "hello"})
    service.observe_chunk(
        agent_id,
        thread_id,
        {"type": "tool_call_chunk", "id": "call_1", "name": "read_file", "args": {"path": "a.py"}},
    )

    metrics = await client.get(_url(agent_id, thread_id, "/metrics"), headers=alice_auth)
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["turns"] == 1
    assert body["steps"] == 2

    exported = await client.get(_url(agent_id, thread_id, "/export"), headers=alice_auth)
    assert exported.status_code == 200, exported.text
    content_type = exported.headers.get("content-type", "")
    assert "text/plain" in content_type or "ndjson" in content_type
    disposition = exported.headers.get("content-disposition", "")
    assert thread_id in disposition
    lines = [line for line in exported.text.splitlines() if line.strip()]
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["kind"] == "user"
    assert parsed[0]["payload"]["content"] == "hello"
    assert parsed[1]["kind"] == "tool"
    assert parsed[1]["payload"]["name"] == "read_file"


async def test_event_detail_missing_is_not_found(env_alice_bob_agent: Any) -> None:
    client, _srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)

    response = await client.get(
        _url(agent_id, thread_id, "/events/missing-event"),
        headers=alice_auth,
    )
    assert response.status_code == 404
