"""HTTP trajectory history, event detail, metrics, export, and live SSE."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any
from urllib.parse import urlencode

from octop.api.routers.chat import trajectory as trajectory_mod


def _url(agent_id: str, thread_id: str, suffix: str = "") -> str:
    return f"/api/agents/{agent_id}/threads/{thread_id}/trajectory{suffix}"


async def _create_thread(client: Any, auth: dict[str, str], agent_id: str) -> str:
    response = await client.post(f"/api/agents/{agent_id}/threads", headers=auth)
    assert response.status_code == 201, response.text
    return str(response.json()["thread_id"])


def _sse_event_payloads(blob: str, event_name: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    current: str | None = None
    for line in blob.splitlines():
        if line.startswith("event:"):
            current = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and current == event_name:
            raw = line.split(":", 1)[1].strip()
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payloads.append(parsed)
            current = None
    return payloads


class _SseStream:
    def __init__(
        self, status_code: int, headers: dict[str, str], chunks: asyncio.Queue[bytes | None]
    ) -> None:
        self.status_code = status_code
        self.headers = headers
        self._chunks = chunks

    async def aiter_text(self) -> AsyncIterator[str]:
        while True:
            chunk = await self._chunks.get()
            if chunk is None:
                return
            yield chunk.decode("utf-8")


@asynccontextmanager
async def _open_asgi_sse(
    app: Any,
    path: str,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
) -> AsyncIterator[_SseStream]:
    """Drive the ASGI app concurrently so infinite SSE can be consumed chunk-wise.

    httpx.ASGITransport buffers the full body and cannot test live streams.
    """
    query = urlencode({key: str(value) for key, value in (params or {}).items()})
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1")) for key, value in headers.items()
    ]
    raw_headers.append((b"host", b"testserver"))
    chunks: asyncio.Queue[bytes | None] = asyncio.Queue()
    started: asyncio.Future[tuple[int, dict[str, str]]] = asyncio.get_running_loop().create_future()
    disconnected = asyncio.Event()
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            header_map = {
                key.decode("latin-1"): value.decode("latin-1")
                for key, value in message.get("headers", [])
            }
            if not started.done():
                started.set_result((int(message["status"]), header_map))
            return
        if message["type"] == "http.response.body":
            body = message.get("body") or b""
            if body:
                await chunks.put(bytes(body))
            if not message.get("more_body", False):
                await chunks.put(None)

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query.encode("ascii"),
        "headers": raw_headers,
        "client": ("127.0.0.1", 123),
        "server": ("testserver", 80),
        "root_path": "",
    }
    task = asyncio.create_task(app(scope, receive, send))
    try:
        status, header_map = await asyncio.wait_for(started, timeout=5)
        yield _SseStream(status, header_map, chunks)
    finally:
        disconnected.set()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def _read_sse_until(response: _SseStream, *, predicate: Any, timeout: float = 5.0) -> str:
    buf = ""

    async def _consume() -> str:
        nonlocal buf
        async for chunk in response.aiter_text():
            buf += chunk
            if predicate(buf):
                return buf
        return buf

    return await asyncio.wait_for(_consume(), timeout=timeout)


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

    response = await client.get(_url(agent_id, thread_id, "/events/any-id"), headers=bob_auth)
    assert response.status_code in (403, 404)

    response = await client.get(_url(agent_id, thread_id, "/stream"), headers=bob_auth)
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
    service.observe_chunk(
        agent_id,
        thread_id,
        {
            "type": "tool_call_chunk",
            "id": "call_1",
            "name": "read_file",
            "args": {"path": "a.py"},
        },
    )
    service.observe_chunk(
        agent_id,
        thread_id,
        {
            "type": "tool_result",
            "id": "call_1",
            "name": "read_file",
            "content": "file contents",
        },
    )

    response = await client.get(_url(agent_id, thread_id), headers=alice_auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["thread_id"] == thread_id
    # user + synthetic ASSISTANT (tool_call_only) + tool
    assert len(body["events"]) == 3
    kinds = [event["kind"] for event in body["events"]]
    assert kinds == ["user", "assistant", "tool"]
    user_event = body["events"][0]
    assistant_event = body["events"][1]
    tool_event = body["events"][2]
    assert "hello there" in user_event["summary"]
    # Message bodies stay on the detail endpoint only.
    assert user_event["payload"].get("content") is None
    assert assistant_event["payload"].get("tool_call_only") is True
    # Tool args/result are available on the list for ledger rendering.
    assert tool_event["payload"]["name"] == "read_file"
    assert tool_event["payload"]["args"] == {"path": "a.py"}
    assert tool_event["payload"]["result"] == "file contents"

    detail = await client.get(
        _url(agent_id, thread_id, f"/events/{user_event['event_id']}"),
        headers=alice_auth,
    )
    assert detail.status_code == 200, detail.text
    full = detail.json()
    assert full["event_id"] == user_event["event_id"]
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
    assert body["steps"] == 3

    exported = await client.get(_url(agent_id, thread_id, "/export"), headers=alice_auth)
    assert exported.status_code == 200, exported.text
    content_type = exported.headers.get("content-type", "")
    assert "text/plain" in content_type or "ndjson" in content_type
    disposition = exported.headers.get("content-disposition", "")
    assert thread_id in disposition
    lines = [line for line in exported.text.splitlines() if line.strip()]
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["kind"] == "user"
    assert parsed[0]["payload"]["content"] == "hello"
    assert parsed[1]["kind"] == "assistant"
    assert parsed[1]["payload"].get("tool_call_only") is True
    assert parsed[2]["kind"] == "tool"
    assert parsed[2]["payload"]["name"] == "read_file"


async def test_event_detail_missing_is_not_found(env_alice_bob_agent: Any) -> None:
    client, _srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)

    response = await client.get(
        _url(agent_id, thread_id, "/events/missing-event"),
        headers=alice_auth,
    )
    assert response.status_code == 404


async def test_live_sse_emits_event_after_subscribe(env_alice_bob_agent: Any) -> None:
    client, srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)
    service = srv.app_runtime.trajectory_service
    assert service is not None

    async with _open_asgi_sse(
        client._octop_app,  # type: ignore[attr-defined]
        _url(agent_id, thread_id, "/stream"),
        alice_auth,
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        published = False

        def _ready(buf: str) -> bool:
            nonlocal published
            if not published and "event: metrics" in buf:
                published = True
                service.observe_chunk(
                    agent_id, thread_id, {"type": "user", "content": "hello live"}
                )
            return any("event_id" in payload for payload in _sse_event_payloads(buf, "event"))

        blob = await _read_sse_until(response, predicate=_ready)

    payloads = _sse_event_payloads(blob, "event")
    assert payloads
    assert payloads[0]["event_id"]
    assert payloads[0]["kind"] == "user"


async def test_live_sse_honors_after_seq(env_alice_bob_agent: Any) -> None:
    client, srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)
    service = srv.app_runtime.trajectory_service
    assert service is not None
    service.observe_chunk(agent_id, thread_id, {"type": "user", "content": "first"})
    service.observe_chunk(agent_id, thread_id, {"type": "user", "content": "second"})
    listed = await client.get(_url(agent_id, thread_id), headers=alice_auth)
    events = listed.json()["events"]
    assert len(events) == 2
    first_id, second_id = events[0]["event_id"], events[1]["event_id"]
    first_seq = int(events[0]["seq"])

    async with _open_asgi_sse(
        client._octop_app,  # type: ignore[attr-defined]
        _url(agent_id, thread_id, "/stream"),
        alice_auth,
        params={"after_seq": first_seq},
    ) as response:
        assert response.status_code == 200
        blob = await _read_sse_until(
            response,
            predicate=lambda buf: any(
                payload.get("event_id") == second_id
                for payload in _sse_event_payloads(buf, "event")
            ),
        )

    event_ids = [payload["event_id"] for payload in _sse_event_payloads(blob, "event")]
    assert second_id in event_ids
    # ``after_seq`` also re-emits the boundary row as an upsert refresh.
    assert first_id in event_ids


async def test_sse_catchup_refreshes_same_seq_tool_after_history(
    env_alice_bob_agent: Any,
) -> None:
    """Tool result upserted before subscribe must still appear in catch-up."""
    client, srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)
    service = srv.app_runtime.trajectory_service
    assert service is not None
    service.observe_chunk(
        agent_id,
        thread_id,
        {
            "type": "tool_call_chunk",
            "id": "call_race",
            "name": "read_file",
            "args": {"path": "a.py"},
        },
    )
    listed = await client.get(_url(agent_id, thread_id), headers=alice_auth)
    tool = next(event for event in listed.json()["events"] if event["kind"] == "tool")
    tool_seq = int(tool["seq"])
    service.observe_chunk(
        agent_id,
        thread_id,
        {
            "type": "tool_result",
            "id": "call_race",
            "name": "read_file",
            "content": "late result",
        },
    )

    async with _open_asgi_sse(
        client._octop_app,  # type: ignore[attr-defined]
        _url(agent_id, thread_id, "/stream"),
        alice_auth,
        params={"after_seq": tool_seq},
    ) as response:
        assert response.status_code == 200
        blob = await _read_sse_until(
            response,
            predicate=lambda buf: any(
                payload.get("kind") == "tool"
                and payload.get("payload", {}).get("result") == "late result"
                for payload in _sse_event_payloads(buf, "event")
            ),
        )

    tool_payloads = [
        payload for payload in _sse_event_payloads(blob, "event") if payload.get("kind") == "tool"
    ]
    assert any(p.get("payload", {}).get("result") == "late result" for p in tool_payloads)


async def test_live_sse_delivers_same_seq_tool_upsert(env_alice_bob_agent: Any) -> None:
    """Tool call → result keeps the same seq; the upsert must still stream."""
    client, srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)
    service = srv.app_runtime.trajectory_service
    assert service is not None

    async with _open_asgi_sse(
        client._octop_app,  # type: ignore[attr-defined]
        _url(agent_id, thread_id, "/stream"),
        alice_auth,
    ) as response:
        assert response.status_code == 200
        phase = 0

        def _ready(buf: str) -> bool:
            nonlocal phase
            payloads = _sse_event_payloads(buf, "event")
            if phase == 0 and "event: metrics" in buf:
                phase = 1
                service.observe_chunk(
                    agent_id,
                    thread_id,
                    {
                        "type": "tool_call_chunk",
                        "id": "call_live",
                        "name": "read_file",
                        "args": {"path": "a.py"},
                    },
                )
            if phase == 1 and any(
                p.get("kind") == "tool" and p.get("payload", {}).get("args") for p in payloads
            ):
                phase = 2
                service.observe_chunk(
                    agent_id,
                    thread_id,
                    {
                        "type": "tool_result",
                        "id": "call_live",
                        "name": "read_file",
                        "content": "file contents",
                    },
                )
            return any(
                p.get("kind") == "tool" and p.get("payload", {}).get("result") == "file contents"
                for p in payloads
            )

        blob = await _read_sse_until(response, predicate=_ready)

    tool_payloads = [
        payload for payload in _sse_event_payloads(blob, "event") if payload.get("kind") == "tool"
    ]
    assert tool_payloads
    assert any(p.get("payload", {}).get("result") == "file contents" for p in tool_payloads)
    seqs = {p.get("seq") for p in tool_payloads}
    assert len(seqs) == 1


async def test_live_sse_emits_heartbeat(env_alice_bob_agent: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(trajectory_mod, "TRAJECTORY_SSE_HEARTBEAT_S", 0.05)
    client, _srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)

    async with _open_asgi_sse(
        client._octop_app,  # type: ignore[attr-defined]
        _url(agent_id, thread_id, "/stream"),
        alice_auth,
    ) as response:
        assert response.status_code == 200
        blob = await _read_sse_until(response, predicate=lambda buf: "event: heartbeat" in buf)
    assert "event: heartbeat" in blob


async def test_delete_thread_cascades_trajectory_ledger(env_alice_bob_agent: Any) -> None:
    client, srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)
    service = srv.app_runtime.trajectory_service
    assert service is not None
    service.observe_chunk(agent_id, thread_id, {"type": "user", "content": "hello"})
    service.observe_chunk(agent_id, thread_id, {"type": "user", "content": "again"})
    assert len(service.list_events(thread_id, before_seq=None, limit=10, kinds=None)) == 2

    response = await client.delete(
        f"/api/agents/{agent_id}/threads/{thread_id}",
        headers=alice_auth,
    )
    assert response.status_code == 204, response.text
    assert service.list_events(thread_id, before_seq=None, limit=10, kinds=None) == []


async def test_delete_thread_succeeds_when_trajectory_cascade_raises(
    env_alice_bob_agent: Any,
) -> None:
    client, srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)
    service = srv.app_runtime.trajectory_service
    assert service is not None
    service.observe_chunk(agent_id, thread_id, {"type": "user", "content": "hello"})

    def _boom(_thread_id: str) -> int:
        raise RuntimeError("ledger down")

    service.delete_for_thread = _boom  # type: ignore[method-assign]

    response = await client.delete(
        f"/api/agents/{agent_id}/threads/{thread_id}",
        headers=alice_auth,
    )
    assert response.status_code == 204, response.text
    listed = await client.get(f"/api/agents/{agent_id}/threads", headers=alice_auth)
    assert listed.status_code == 200
    assert all(item["thread_id"] != thread_id for item in listed.json())


async def test_live_sse_unsubscribes_on_cancel(env_alice_bob_agent: Any) -> None:
    client, srv, alice_auth, _bob_auth, agent_id = env_alice_bob_agent
    thread_id = await _create_thread(client, alice_auth, agent_id)
    service = srv.app_runtime.trajectory_service
    assert service is not None
    bus = service._bus  # noqa: SLF001

    async with _open_asgi_sse(
        client._octop_app,  # type: ignore[attr-defined]
        _url(agent_id, thread_id, "/stream"),
        alice_auth,
    ) as response:
        assert response.status_code == 200
        await _read_sse_until(response, predicate=lambda buf: "event: metrics" in buf)
        assert thread_id in bus._subscribers  # noqa: SLF001

    await asyncio.sleep(0.05)
    assert not bus._subscribers.get(thread_id)  # noqa: SLF001
