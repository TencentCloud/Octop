"""tests/integration/test_chat_ws.py — dashboard WebSocket chat + thread CRUD."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.support.app import octop_client
from tests.support.auth import (
    auth_header,
    bootstrap_admin,
    create_agent,
    ensure_users,
    seed_openai_provider,
)
from tests.support.fakes import FakeHarnessAgent
from tests.support.http import ws_token


@pytest.fixture
async def env(tmp_octop_home: Path) -> AsyncIterator[Any]:
    fake = FakeHarnessAgent(
        chunks=[
            {"type": "token", "node": "agent", "content": "Hello "},
            {"type": "token", "node": "agent", "content": "Bob."},
        ]
    )
    async with octop_client(tmp_octop_home, fake_agent=fake) as (c, srv):
        await bootstrap_admin(c, tmp_octop_home)
        admin_auth = await auth_header(c)
        await seed_openai_provider(c, admin_auth)
        users = await ensure_users(c, admin_auth, "alice", "bob")
        aid = await create_agent(c, users["alice"])
        yield c, srv, fake, users["alice"], users["bob"], aid


def _consume_ws_turn_sync(
    app: object,
    aid: str,
    token: str,
    body: dict[str, Any],
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    with TestClient(app).websocket_connect(  # type: ignore[attr-defined]
        f"/api/agents/{aid}/chat/ws?token={token}"
    ) as ws:
        ws.send_json(body)
        while True:
            raw = ws.receive_text()
            chunk = json.loads(raw)
            chunks.append(chunk)
            if chunk.get("type") in ("done", "error"):
                break
    return chunks


def _disconnect_ws_turn_sync(
    app: object,
    aid: str,
    token: str,
) -> None:
    with TestClient(app).websocket_connect(  # type: ignore[attr-defined]
        f"/api/agents/{aid}/chat/ws?token={token}"
    ) as ws:
        ws.send_json({"type": "user_turn", "text": "cancel me"})
        ws.receive_text()


def _turn_then_rebind_sync(
    app: object,
    aid: str,
    token: str,
    thread_id: str,
    gate_release: Any,
) -> list[dict[str, Any]]:
    """Start a turn on conn A, drop it after the first token, re-subscribe on B.

    The fake stream is gated between first and second token so B can subscribe
    while the turn is still active, then receive the remaining chunks.
    """
    with TestClient(app).websocket_connect(  # type: ignore[attr-defined]
        f"/api/agents/{aid}/chat/ws?token={token}"
    ) as ws_a:
        ws_a.send_json(
            {
                "type": "user_turn",
                "text": "slow please",
                "thread_id": thread_id,
            }
        )
        first = json.loads(ws_a.receive_text())
        assert first.get("type") == "token"
        assert first.get("content") == "first"
    # A is closed; turn is blocked on gate_release (still active, not cancelled).

    frames: list[dict[str, Any]] = []
    with TestClient(app).websocket_connect(  # type: ignore[attr-defined]
        f"/api/agents/{aid}/chat/ws?token={token}"
    ) as ws_b:
        ws_b.send_json({"type": "subscribe", "thread_id": thread_id})
        status = json.loads(ws_b.receive_text())
        frames.append(status)
        # Release the slow stream only after B is subscribed.
        gate_release.set()
        for _ in range(50):
            raw = ws_b.receive_text()
            frame = json.loads(raw)
            frames.append(frame)
            if frame.get("type") in ("done", "error"):
                break
    return frames


async def test_ws_rebind_after_disconnect_receives_later_chunks(env: Any) -> None:
    """After disconnect, a new subscriber must see subsequent tokens + done."""
    c, srv, _fake, alice_auth, _bob_auth, aid = env
    create = await c.post(f"/api/agents/{aid}/threads", headers=alice_auth)
    tid = create.json()["thread_id"]
    agent = srv.app_runtime.agent_registry.get_agent(aid)

    gate = asyncio.Event()

    async def slow_stream(request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "token", "node": "agent", "content": "first"}
        await gate.wait()
        yield {"type": "token", "node": "agent", "content": "second"}

    agent.stream = slow_stream
    cancel_spy = MagicMock(wraps=srv.app_runtime.agent_registry.cancel_stream)
    srv.app_runtime.agent_registry.cancel_stream = cancel_spy

    frames = await asyncio.to_thread(
        _turn_then_rebind_sync,
        c._octop_app,  # type: ignore[attr-defined]
        aid,
        ws_token(alice_auth),
        tid,
        gate,
    )

    cancel_spy.assert_not_called()
    assert frames[0] == {"type": "turn_status", "thread_id": tid, "active": True}
    contents = [f.get("content") for f in frames if f.get("type") == "token"]
    assert "second" in contents
    assert frames[-1].get("type") == "done"


async def _consume_ws_turn(
    c: httpx.AsyncClient,
    aid: str,
    auth: dict[str, str],
    *,
    text: str = "Hello",
    thread_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    body: dict[str, Any] = {
        "type": "user_turn",
        "text": text,
        "messages": [{"role": "user", "content": text}],
    }
    if thread_id:
        body["thread_id"] = thread_id
    if extra:
        body.update(extra)

    # Run the blocking starlette TestClient session in a worker thread so the
    # server's event loop stays free to process the turn (see ws_chat_turn).
    return await asyncio.to_thread(
        _consume_ws_turn_sync,
        c._octop_app,  # type: ignore[attr-defined]
        aid,
        ws_token(auth),
        body,
    )


async def test_ws_emits_chunks_then_done(env: Any) -> None:
    c, _srv, _fake, alice_auth, _bob_auth, aid = env
    chunks = await _consume_ws_turn(c, aid, alice_auth)
    await asyncio.sleep(0.05)
    types = [ch.get("type") for ch in chunks]
    assert "token" in types
    assert chunks[-1]["type"] == "done"


async def test_ws_disconnect_does_not_cancel_active_turn(env: Any) -> None:
    c, srv, _fake, alice_auth, _bob_auth, aid = env
    agent = srv.app_runtime.agent_registry.get_agent(aid)

    async def slow_stream(request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "token", "node": "agent", "content": "started"}
        await asyncio.sleep(1)

    agent.stream = slow_stream
    original_cancel = srv.app_runtime.agent_registry.cancel_stream
    cancel_spy = MagicMock(wraps=original_cancel)
    srv.app_runtime.agent_registry.cancel_stream = cancel_spy

    await asyncio.to_thread(
        _disconnect_ws_turn_sync,
        c._octop_app,  # type: ignore[attr-defined]
        aid,
        ws_token(alice_auth),
    )

    await asyncio.sleep(0.05)
    cancel_spy.assert_not_called()


def _subscribe_ws_sync(
    app: object,
    aid: str,
    token: str,
    thread_id: str,
) -> dict[str, Any]:
    with TestClient(app).websocket_connect(  # type: ignore[attr-defined]
        f"/api/agents/{aid}/chat/ws?token={token}"
    ) as ws:
        ws.send_json({"type": "subscribe", "thread_id": thread_id})
        return json.loads(ws.receive_text())


async def test_ws_subscribe_turn_status_idle(env: Any) -> None:
    c, _srv, _fake, alice_auth, _bob_auth, aid = env
    create = await c.post(f"/api/agents/{aid}/threads", headers=alice_auth)
    assert create.status_code == 201
    tid = create.json()["thread_id"]

    frame = await asyncio.to_thread(
        _subscribe_ws_sync,
        c._octop_app,  # type: ignore[attr-defined]
        aid,
        ws_token(alice_auth),
        tid,
    )
    assert frame == {"type": "turn_status", "thread_id": tid, "active": False}


def _cancel_ws_turn_sync(
    app: object,
    aid: str,
    token: str,
    thread_id: str,
) -> None:
    with TestClient(app).websocket_connect(  # type: ignore[attr-defined]
        f"/api/agents/{aid}/chat/ws?token={token}"
    ) as ws:
        ws.send_json({"type": "user_turn", "text": "cancel me", "thread_id": thread_id})
        ws.receive_text()  # first token
        ws.send_json({"type": "cancel", "thread_id": thread_id})


async def test_ws_cancel_frame_cancels_active_turn(env: Any) -> None:
    c, srv, _fake, alice_auth, _bob_auth, aid = env
    agent = srv.app_runtime.agent_registry.get_agent(aid)
    create = await c.post(f"/api/agents/{aid}/threads", headers=alice_auth)
    tid = create.json()["thread_id"]

    async def slow_stream(request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "token", "node": "agent", "content": "started"}
        await asyncio.sleep(1)

    agent.stream = slow_stream
    original_cancel = srv.app_runtime.agent_registry.cancel_stream
    cancel_spy = MagicMock(wraps=original_cancel)
    srv.app_runtime.agent_registry.cancel_stream = cancel_spy

    await asyncio.to_thread(
        _cancel_ws_turn_sync,
        c._octop_app,  # type: ignore[attr-defined]
        aid,
        ws_token(alice_auth),
        tid,
    )

    for _ in range(40):
        if cancel_spy.called:
            break
        await asyncio.sleep(0.01)
    cancel_spy.assert_called()
    assert cancel_spy.call_args.args[0] == aid
    assert cancel_spy.call_args.args[1] == tid


async def test_ws_emits_error_frame_on_exception(env: Any) -> None:
    c, srv, _fake, alice_auth, _bob_auth, aid = env
    agent = srv.app_runtime.agent_registry.get_agent(aid)
    agent.raise_on_stream = RuntimeError("upstream blew up")

    chunks = await _consume_ws_turn(c, aid, alice_auth, text="err")
    assert chunks[-1]["type"] == "error"


async def test_ws_bad_agent_rejected(env: Any) -> None:
    c, _srv, _fake, alice_auth, _bob_auth, _aid = env
    with (
        pytest.raises(WebSocketDisconnect),
        TestClient(c._octop_app).websocket_connect(  # type: ignore[attr-defined]
            f"/api/agents/01HMISSING0000000000000000/chat/ws?token={ws_token(alice_auth)}"
        ),
    ):
        pass


async def test_ws_cross_user_rejected(env: Any) -> None:
    c, _srv, _fake, _admin_auth, bob_auth, aid = env
    with (
        pytest.raises(WebSocketDisconnect),
        TestClient(c._octop_app).websocket_connect(  # type: ignore[attr-defined]
            f"/api/agents/{aid}/chat/ws?token={ws_token(bob_auth)}"
        ),
    ):
        pass


async def test_ws_accepts_skills_and_model(env: Any) -> None:
    c, _srv, _fake, auth, _bob_auth, aid = env
    chunks = await _consume_ws_turn(
        c,
        aid,
        auth,
        extra={"skills": [], "model": "openai/gpt-4o"},
    )
    assert chunks[-1]["type"] == "done"


async def test_polish_rejects_empty_text(env: Any) -> None:
    c, _srv, _fake, alice_auth, _bob_auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/chat/polish",
        headers=alice_auth,
        json={"text": "   "},
    )
    assert r.status_code == 400


async def test_threads_list_after_stream(env: Any) -> None:
    c, _srv, _fake, alice_auth, _bob_auth, aid = env
    await _consume_ws_turn(c, aid, alice_auth, text="What's up?")
    await asyncio.sleep(0.05)

    r = await c.get(f"/api/agents/{aid}/threads", headers=alice_auth)
    assert r.status_code == 200
    threads = r.json()
    assert len(threads) >= 1
    assert any(t.get("has_messages") for t in threads)


async def test_thread_history_after_stream(env: Any) -> None:
    c, _srv, _fake, alice_auth, _bob_auth, aid = env
    await _consume_ws_turn(c, aid, alice_auth, text="History test")
    await asyncio.sleep(0.05)

    r = await c.get(f"/api/agents/{aid}/threads", headers=alice_auth)
    tid = r.json()[0]["thread_id"]
    hist = await c.get(f"/api/agents/{aid}/threads/{tid}/history", headers=alice_auth)
    assert hist.status_code == 200
    assert "messages" in hist.json()


async def test_create_thread(env: Any) -> None:
    c, _srv, _fake, alice_auth, _bob_auth, aid = env
    r = await c.post(f"/api/agents/{aid}/threads", headers=alice_auth)
    assert r.status_code == 201
    body = r.json()
    assert "thread_id" in body
    assert "session_key" in body
