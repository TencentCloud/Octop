"""tests/integration/test_chat_ws.py — dashboard WebSocket chat + thread CRUD."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
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
from tests.support.http import chat_ws_path, ws_connect


def _chat_ws(c: httpx.AsyncClient, aid: str, auth: dict[str, str]) -> Any:
    return ws_connect(c._octop_app, chat_ws_path(aid, auth))  # type: ignore[attr-defined]


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


async def _turn_then_rebind(
    c: httpx.AsyncClient,
    aid: str,
    auth: dict[str, str],
    thread_id: str,
    gate_release: asyncio.Event,
) -> list[dict[str, Any]]:
    """Start a turn on conn A, drop it after the first token, re-subscribe on B.

    The fake stream is gated between first and second token so B can subscribe
    while the turn is still active, then receive the remaining chunks.
    """
    async with _chat_ws(c, aid, auth) as ws_a:
        await ws_a.send_json(
            {
                "type": "user_turn",
                "text": "slow please",
                "thread_id": thread_id,
            }
        )
        first = await ws_a.receive_json()
        assert first.get("type") == "token"
        assert first.get("content") == "first"
    # A is closed; turn is blocked on gate_release (still active, not cancelled).

    frames: list[dict[str, Any]] = []
    async with _chat_ws(c, aid, auth) as ws_b:
        await ws_b.send_json({"type": "subscribe", "thread_id": thread_id})
        frames.append(await ws_b.receive_json())
        # Release the slow stream only after B is subscribed.
        gate_release.set()
        frames.extend(await ws_b.drain_turn())
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

    frames = await _turn_then_rebind(c, aid, alice_auth, tid, gate)

    cancel_spy.assert_not_called()
    assert frames[0] == {"type": "turn_status", "thread_id": tid, "active": True}
    contents = [f.get("content") for f in frames if f.get("type") == "token"]
    assert "second" in contents
    assert frames[-1].get("type") == "done"


async def _turn_with_second_subscriber(
    c: httpx.AsyncClient,
    aid: str,
    auth: dict[str, str],
    thread_id: str,
    gate_release: asyncio.Event,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep conn A open, subscribe conn B mid-turn; both receive remaining chunks."""
    a_frames: list[dict[str, Any]] = []
    b_frames: list[dict[str, Any]] = []
    async with _chat_ws(c, aid, auth) as ws_a:
        await ws_a.send_json(
            {
                "type": "user_turn",
                "text": "slow please",
                "thread_id": thread_id,
            }
        )
        a_frames.append(await ws_a.receive_json())
        async with _chat_ws(c, aid, auth) as ws_b:
            await ws_b.send_json({"type": "subscribe", "thread_id": thread_id})
            b_frames.append(await ws_b.receive_json())
            gate_release.set()
            rest_a, rest_b = await asyncio.gather(ws_a.drain_turn(), ws_b.drain_turn())
            a_frames.extend(rest_a)
            b_frames.extend(rest_b)
    return a_frames, b_frames


async def _two_threads_turn(
    c: httpx.AsyncClient,
    aid: str,
    auth: dict[str, str],
    tid_a: str,
    tid_b: str,
    *,
    text_a: str = "one",
    text_b: str = "two",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run two live turns on different threads over two concurrent sockets."""
    body_a: dict[str, Any] = {
        "type": "user_turn",
        "text": text_a,
        "messages": [{"role": "user", "content": text_a}],
        "thread_id": tid_a,
    }
    body_b: dict[str, Any] = {
        "type": "user_turn",
        "text": text_b,
        "messages": [{"role": "user", "content": text_b}],
        "thread_id": tid_b,
    }
    async with _chat_ws(c, aid, auth) as ws_a, _chat_ws(c, aid, auth) as ws_b:
        await ws_a.send_json(body_a)
        await ws_b.send_json(body_b)
        return await asyncio.gather(ws_a.drain_turn(), ws_b.drain_turn())  # type: ignore[return-value]


async def test_ws_concurrent_subscribers_both_receive_later_chunks(env: Any) -> None:
    """Two dashboard sockets on the same thread both get live tokens."""
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

    a_frames, b_frames = await _turn_with_second_subscriber(c, aid, alice_auth, tid, gate)

    assert a_frames[0].get("content") == "first"
    assert [f.get("content") for f in a_frames if f.get("type") == "token"] == ["first", "second"]
    assert a_frames[-1].get("type") == "done"
    assert b_frames[0] == {"type": "turn_status", "thread_id": tid, "active": True}
    assert [f.get("content") for f in b_frames if f.get("type") == "token"] == ["second"]
    assert b_frames[-1].get("type") == "done"


async def test_ws_two_threads_do_not_cross_stream(env: Any) -> None:
    """Two live turns on different threads must not mix tokens across sockets."""
    c, srv, _fake, alice_auth, _bob_auth, aid = env
    create_a = await c.post(f"/api/agents/{aid}/threads", headers=alice_auth)
    create_b = await c.post(f"/api/agents/{aid}/threads", headers=alice_auth)
    tid_a = create_a.json()["thread_id"]
    tid_b = create_b.json()["thread_id"]
    agent = srv.app_runtime.agent_registry.get_agent(aid)

    async def tagged_stream(request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        tid = str(request.get("thread_id") or "")
        yield {"type": "token", "node": "agent", "content": f"from-{tid}"}

    agent.stream = tagged_stream

    a_frames, b_frames = await _two_threads_turn(c, aid, alice_auth, tid_a, tid_b)

    a_tokens = [f.get("content") for f in a_frames if f.get("type") == "token"]
    b_tokens = [f.get("content") for f in b_frames if f.get("type") == "token"]
    assert a_tokens == [f"from-{tid_a}"]
    assert b_tokens == [f"from-{tid_b}"]
    assert all(f.get("thread_id") == tid_a for f in a_frames if f.get("type") in ("token", "done"))
    assert all(f.get("thread_id") == tid_b for f in b_frames if f.get("type") in ("token", "done"))


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

    async with _chat_ws(c, aid, auth) as ws:
        await ws.send_json(body)
        return await ws.drain_turn()


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

    async with _chat_ws(c, aid, alice_auth) as ws:
        await ws.send_json({"type": "user_turn", "text": "cancel me"})
        await ws.receive_json()

    await asyncio.sleep(0.05)
    cancel_spy.assert_not_called()


async def _subscribe_ws(
    c: httpx.AsyncClient,
    aid: str,
    auth: dict[str, str],
    thread_id: str,
) -> dict[str, Any]:
    async with _chat_ws(c, aid, auth) as ws:
        await ws.send_json({"type": "subscribe", "thread_id": thread_id})
        return await ws.receive_json()


async def test_ws_subscribe_turn_status_idle(env: Any) -> None:
    c, _srv, _fake, alice_auth, _bob_auth, aid = env
    create = await c.post(f"/api/agents/{aid}/threads", headers=alice_auth)
    assert create.status_code == 201
    tid = create.json()["thread_id"]

    frame = await _subscribe_ws(c, aid, alice_auth, tid)
    assert frame == {"type": "turn_status", "thread_id": tid, "active": False}


async def test_ws_subscribe_rejects_another_users_thread(env: Any) -> None:
    c, _srv, _fake, alice_auth, bob_auth, aid = env
    response = await c.patch(
        f"/api/agents/{aid}",
        headers=alice_auth,
        json={"is_shared": True},
    )
    assert response.status_code == 200, response.text

    response = await c.post(f"/api/agents/{aid}/threads", headers=bob_auth)
    assert response.status_code == 201, response.text
    tid = response.json()["thread_id"]

    frame = await _subscribe_ws(c, aid, alice_auth, tid)
    assert frame == {"type": "error", "message": f"thread {tid!r} not found"}


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

    async with _chat_ws(c, aid, alice_auth) as ws:
        await ws.send_json({"type": "user_turn", "text": "cancel me", "thread_id": tid})
        await ws.receive_json()  # first token
        await ws.send_json({"type": "cancel", "thread_id": tid})

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


# X2 (PLAN §2): the access decision moved *after* ``accept()`` so the client can
# observe the close frame and degrade in ``onclose``. These two cases therefore
# assert the close explicitly: keeping the old ``pytest.raises`` around
# ``connect()`` would leave a passing body that never observes the refusal — the
# criterion would go silently green, which is worse than breaking it.
async def test_ws_bad_agent_rejected(env: Any) -> None:
    c, _srv, _fake, alice_auth, _bob_auth, _aid = env
    async with _chat_ws(c, "01HMISSING0000000000000000", alice_auth) as websocket:
        # entering the block succeeded — proof the refusal moved past the handshake
        with pytest.raises(WebSocketDisconnect) as caught:
            await websocket.receive_json()
    assert caught.value.code == 4404


async def test_ws_cross_user_rejected(env: Any) -> None:
    c, _srv, _fake, _admin_auth, bob_auth, aid = env
    async with _chat_ws(c, aid, bob_auth) as websocket:
        with pytest.raises(WebSocketDisconnect) as caught:
            await websocket.receive_json()
    # Pinned on purpose: the agent-side refusal is ``ErrorCode.FORBIDDEN``, which
    # maps to 4003 (``ws.py``: ``code = 4003 if exc.code == FORBIDDEN else 4404``).
    # A loose ``in (4003, 4404)`` would also accept a *project*-side code here and
    # could not tell the two gates apart.
    assert caught.value.code == 4003, f"agent-side refusal must be 4003: {caught.value}"


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


async def test_thread_history_reports_active_turn(env: Any) -> None:
    """History must expose whether a turn is still running, so a reloaded
    dashboard can re-subscribe instead of guessing from the message list."""
    c, srv, _fake, alice_auth, _bob_auth, aid = env
    create = await c.post(f"/api/agents/{aid}/threads", headers=alice_auth)
    tid = create.json()["thread_id"]

    idle = await c.get(f"/api/agents/{aid}/threads/{tid}/history", headers=alice_auth)
    assert idle.json()["turn_active"] is False

    srv.app_runtime.gateway.ws_hub.mark_turn_active(tid)
    active = await c.get(f"/api/agents/{aid}/threads/{tid}/history", headers=alice_auth)
    assert active.json()["turn_active"] is True


async def test_create_thread(env: Any) -> None:
    c, _srv, _fake, alice_auth, _bob_auth, aid = env
    r = await c.post(f"/api/agents/{aid}/threads", headers=alice_auth)
    assert r.status_code == 201
    body = r.json()
    assert "thread_id" in body
    assert "session_key" in body


async def test_fork_thread_from_assistant_message(env: Any) -> None:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    c, srv, _fake, alice_auth, bob_auth, aid = env
    created = await c.post(f"/api/agents/{aid}/threads", headers=alice_auth)
    source_id = created.json()["thread_id"]
    agent = srv.app_runtime.agent_registry.get_agent(aid)
    agent.seed_thread_messages(
        source_id,
        [
            HumanMessage(content="first question", id="h1"),
            AIMessage(content="first answer", id="a1"),
            ToolMessage(content="tool-out", id="t1", tool_call_id="c1"),
            HumanMessage(content="second question", id="h2"),
            AIMessage(content="second answer", id="a2"),
        ],
    )

    forked = await c.post(
        f"/api/agents/{aid}/threads/{source_id}/fork",
        headers=alice_auth,
        json={
            "message_id": "a1",
            "content": "first answer",
            "assistant_turns_from_end": 2,
        },
    )
    assert forked.status_code == 201, forked.text
    body = forked.json()
    dest_id = body["thread_id"]
    assert dest_id != source_id
    assert body["source_thread_id"] == source_id
    assert body["copied_messages"] == 2

    history = await c.get(
        f"/api/agents/{aid}/threads/{dest_id}/history",
        headers=alice_auth,
    )
    assert history.status_code == 200
    roles = [m["role"] for m in history.json()["messages"]]
    texts = []
    for msg in history.json()["messages"]:
        content = msg.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(str(block.get("text") or ""))
                elif isinstance(block, dict) and block.get("type") == "tool_result":
                    texts.append(str(block.get("output") or ""))
    assert "user" in roles
    assert "assistant" in roles
    assert "first question" in texts
    assert "first answer" in texts
    assert "second question" not in texts
    assert "second answer" not in texts

    source_history = await c.get(
        f"/api/agents/{aid}/threads/{source_id}/history",
        headers=alice_auth,
    )
    source_texts: list[str] = []
    for msg in source_history.json()["messages"]:
        content = msg.get("content")
        if isinstance(content, str):
            source_texts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    source_texts.append(str(block.get("text") or ""))
    assert "first question" in source_texts
    assert "second question" in source_texts

    denied = await c.post(
        f"/api/agents/{aid}/threads/{source_id}/fork",
        headers=bob_auth,
        json={"message_id": "a1", "assistant_turns_from_end": 2},
    )
    assert denied.status_code in {403, 404}


# ── batch 10 (T-WS-GATE-ii): the handshake-time refusal (F-1) ────────────────
#
# X2 moved the *access* decision past ``accept()``; authentication did **not**
# move — ``ws.py`` closes with 4001 before accepting when the token is missing or
# unresolvable. That dimension had **zero** coverage in this file, so a future
# change that moved the token check after ``accept()`` would have had no CI signal.


async def test_ws_bad_token_is_rejected_in_the_handshake(env: Any) -> None:
    """A malformed token is refused *before* ``accept()`` → code 4001."""
    c, _srv, _fake, _alice_auth, _bob_auth, aid = env
    bad_auth = {"Authorization": "Bearer not-a-real-token"}

    with pytest.raises(WebSocketDisconnect) as caught:
        async with _chat_ws(c, aid, bad_auth):
            pass
    assert caught.value.code == 4001, f"handshake refusal must stay at 4001: {caught.value}"


async def test_ws_missing_token_is_rejected_in_the_handshake(env: Any) -> None:
    """The other 4001 branch: no token at all (`ws.py` @41).

    Built by hand because ``chat_ws_path`` always appends ``?token=`` — the point
    here is precisely the request that carries none.
    """
    c, _srv, _fake, _alice_auth, _bob_auth, aid = env
    with pytest.raises(WebSocketDisconnect) as caught:
        async with ws_connect(c._octop_app, f"/api/agents/{aid}/chat/ws"):  # type: ignore[attr-defined]
            pass
    assert caught.value.code == 4001


# ── batch 10 (T-WS-INT): project context over a real websocket ───────────────
#
# The pair below is the point: A2 closes the batch-four gap (a non-member who can
# reach the agent used to pass), while A4 is the red line (the ordinary
# ``chatStore`` path sends no ``project_id`` and must keep working). Only A2 would
# prove someone is blocked; only A4 would prove nobody is newly blocked.
PROJECTS = "/api/projects"


async def test_ws_project_context_gates_only_when_a_project_is_named(env: Any) -> None:
    """A4 (no project_id ⇒ allowed) and A2 (foreign project_id ⇒ refused, 4404)."""
    c, _srv, _fake, alice_auth, bob_auth, aid = env

    # A4 — the existing dashboard path: no project context, turn runs to ``done``.
    plain = await _consume_ws_turn(c, aid, alice_auth, text="A4")
    assert plain[-1]["type"] == "done", plain

    # A2 — alice owns the agent but is **not** a member of bob's project. The
    # project gate is `PROJECT_WRITE`; `PROJECT_FORBIDDEN` is not `FORBIDDEN`, so
    # the client observes 4404 (not 4003).
    created = await c.post(PROJECTS, headers=bob_auth, json={"name": "A2", "status": "active"})
    assert created.status_code == 201, created.text
    foreign_pid = created.json()["project_id"]

    with pytest.raises(WebSocketDisconnect) as caught:
        await _consume_ws_turn(c, aid, alice_auth, text="A2", extra={"project_id": foreign_pid})
    assert caught.value.code == 4404, f"project-side refusal must be 4404: {caught.value}"


async def test_ws_project_context_accepts_a_member_and_refuses_the_rest(env: Any) -> None:
    """A1 / A6 here; A3 is `test_ws_cross_user_rejected` (4003) and A5 below.

    A1 — alice owns both the agent and the project ⇒ the turn runs to ``done``.
    A6 — a project id that does not exist is refused with the existing code
    (``PROJECT_NOT_FOUND`` → 4404); no new codes were introduced.
    """
    c, _srv, _fake, alice_auth, _bob_auth, aid = env

    mine = await c.post(PROJECTS, headers=alice_auth, json={"name": "A1", "status": "active"})
    assert mine.status_code == 201, mine.text
    pid = mine.json()["project_id"]

    framed = await _consume_ws_turn(c, aid, alice_auth, text="A1", extra={"project_id": pid})
    assert framed[-1]["type"] == "done", framed

    with pytest.raises(WebSocketDisconnect) as caught:
        await _consume_ws_turn(
            c, aid, alice_auth, text="A6", extra={"project_id": "prj_does_not_exist"}
        )
    assert caught.value.code == 4404, caught.value


async def test_ws_project_context_refuses_a_viewer(env: Any) -> None:
    """A5 — a viewer holds ``read`` but not ``write``: refused with 4404.

    WS口径: the refusal arrives as a **close code**, not an HTTP 403.
    """
    c, _srv, _fake, alice_auth, _bob_auth, aid = env
    admin_auth = await auth_header(c)
    pid = (
        await c.post(PROJECTS, headers=alice_auth, json={"name": "A5", "status": "active"})
    ).json()["project_id"]
    admin_id = next(
        u["id"]
        for u in (await c.get("/api/users", headers=admin_auth)).json()
        if u["username"] == "admin"
    )
    added = await c.post(
        f"{PROJECTS}/{pid}/members",
        headers=alice_auth,
        json={"subject_type": "user", "subject_id": str(admin_id), "role": "viewer"},
    )
    assert added.status_code == 201, added.text

    with pytest.raises(WebSocketDisconnect) as caught:
        await _consume_ws_turn(c, aid, admin_auth, text="A5", extra={"project_id": pid})
    assert caught.value.code == 4404, caught.value
