"""Long peer work must not occupy the Bridge receive pump."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from octop.infra.bridge.manager import BridgeManager
from octop.infra.bridge.transport import BridgeSession


@pytest.fixture
async def bridge_pair() -> AsyncIterator[SimpleNamespace]:
    queues: list[asyncio.Queue[str]] = [asyncio.Queue(), asyncio.Queue()]
    gates = [asyncio.Event(), asyncio.Event()]
    tokens = [asyncio.Event(), asyncio.Event()]
    slow_tunnel_started = asyncio.Event()
    slow_tunnel_gate = asyncio.Event()
    managers: list[BridgeManager] = []
    sessions: list[BridgeSession] = []
    hubs: list[dict[str, Any]] = []
    jobs: list[asyncio.Task[None]] = []
    frames: list[list[dict[str, Any]]] = [[], []]

    def make_manager(side: int) -> BridgeManager:
        repo = MagicMock()
        repo.get.return_value = SimpleNamespace(owner_user_id=1)
        manager = BridgeManager(
            bridge_repo=repo,
            secret_repo=MagicMock(),
            user_repo=MagicMock(),
            advertise_base_url="http://local.test",
        )
        senders: dict[str, Any] = {}
        hubs.append(senders)

        def register(key: str, send: Any, **_kwargs: Any) -> None:
            senders[key] = send

        def enqueue(_channel: str, inbound: Any) -> None:
            async def run() -> None:
                send = senders[inbound.ws_connection_id]
                await send({"type": "token", "content": "first token"})
                await gates[side].wait()
                await send({"type": "done"})

            jobs.append(asyncio.create_task(run()))

        async def runner(**kwargs: Any) -> Any:
            return SimpleNamespace(
                thread_id=f"thread-{side}",
                inbound=SimpleNamespace(ws_connection_id=kwargs["ws_connection_id"]),
            )

        runtime = SimpleNamespace(
            user_manager=SimpleNamespace(
                get_by_id=lambda _id: SimpleNamespace(id=1, username="test"),
            ),
            gateway=SimpleNamespace(
                ws_hub=SimpleNamespace(
                    register=register,
                    subscribe=lambda *_args: None,
                    unregister=lambda key: senders.pop(key, None),
                ),
                channel_manager=SimpleNamespace(enqueue=enqueue),
            ),
        )
        manager.bind_asgi_app(
            SimpleNamespace(
                state=SimpleNamespace(octop_server=SimpleNamespace(app_runtime=runtime))
            ),
            peer_turn_runner=runner,
        )
        return manager

    for side in range(2):
        manager = make_manager(side)

        async def send_text(text: str, peer: int = 1 - side) -> None:
            await queues[peer].put(text)

        async def tunnel_handler(payload: dict[str, Any]) -> dict[str, Any]:
            if payload["path"] == "/slow":
                slow_tunnel_started.set()
                await slow_tunnel_gate.wait()
            return {"status": 200, "headers": {}, "body_b64": ""}

        session = BridgeSession(
            connection_id="conn",
            send_text=send_text,
            on_turn_frame=lambda p, m=manager: m._handle_inbound_turn("conn", p),
            on_tunnel_request=tunnel_handler,
        )
        await manager._register_session("conn", session)
        managers.append(manager)
        sessions.append(session)

    async def pump(side: int) -> None:
        # Both production WS readers await handle_message one frame at a time.
        while True:
            await sessions[side].handle_message(await queues[side].get())

    pumps = [asyncio.create_task(pump(side)) for side in range(2)]

    async def on_frame(frame: dict[str, Any], side: int) -> None:
        frames[side].append(frame)
        if frame["type"] == "token":
            tokens[side].set()

    turns = [
        asyncio.create_task(
            managers[side].relay_user_turn(
                connection_id="conn",
                owner_user_id=1,
                remote_agent_id="expert",
                turn_payload={"text": "long task"},
                on_frame=lambda frame, s=side: on_frame(frame, s),
            )
        )
        for side in range(2)
    ]
    try:
        yield SimpleNamespace(
            managers=managers,
            sessions=sessions,
            gates=gates,
            tokens=tokens,
            turns=turns,
            frames=frames,
            hubs=hubs,
            slow_tunnel_started=slow_tunnel_started,
            slow_tunnel_gate=slow_tunnel_gate,
        )
    finally:
        await asyncio.gather(*(session.close() for session in sessions))
        for task in pumps + turns + jobs:
            task.cancel()
        await asyncio.gather(*pumps, *turns, *jobs, return_exceptions=True)


@pytest.mark.asyncio
async def test_bidirectional_tokens_and_tunnels_arrive_before_turns_end(
    bridge_pair: SimpleNamespace,
) -> None:
    pair = bridge_pair
    await asyncio.wait_for(asyncio.gather(*(token.wait() for token in pair.tokens)), timeout=2)
    assert all(not turn.done() for turn in pair.turns)
    assert all(not gate.is_set() for gate in pair.gates)

    slow = asyncio.create_task(pair.sessions[0].tunnel_request(method="GET", path="/slow"))
    try:
        await asyncio.wait_for(pair.slow_tunnel_started.wait(), timeout=2)
        response = await pair.sessions[0].tunnel_request(
            method="GET",
            path="/api/agents",
            timeout=2,
        )
        assert response["status"] == 200
        assert not slow.done()
        assert all(not turn.done() for turn in pair.turns)
        pair.slow_tunnel_gate.set()
        assert (await asyncio.wait_for(slow, timeout=2))["status"] == 200
        for gate in pair.gates:
            gate.set()
        await asyncio.wait_for(asyncio.gather(*pair.turns), timeout=2)
        assert all(any(frame["type"] == "done" for frame in frames) for frames in pair.frames)
    finally:
        slow.cancel()
        await asyncio.gather(slow, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("replace", [False, True], ids=["disconnect", "replace-session"])
async def test_session_close_cleans_handlers_and_local_waiters(
    bridge_pair: SimpleNamespace,
    replace: bool,
) -> None:
    pair = bridge_pair
    await asyncio.wait_for(asyncio.gather(*(token.wait() for token in pair.tokens)), timeout=2)
    pending = asyncio.create_task(pair.sessions[0].tunnel_request(method="GET", path="/slow"))
    await asyncio.wait_for(pair.slow_tunnel_started.wait(), timeout=2)
    assert all(session._handler_tasks for session in pair.sessions)

    if replace:
        replacement = BridgeSession(connection_id="conn", send_text=pair.sessions[0]._send_text)
        await pair.managers[0]._register_session("conn", replacement)
    else:
        await pair.managers[0].disconnect("conn")

    with pytest.raises(ConnectionError, match="bridge session closed"):
        await asyncio.wait_for(pending, timeout=2)
    with pytest.raises(ConnectionError, match="bridge session closed"):
        await asyncio.wait_for(pair.turns[0], timeout=2)
    assert pair.sessions[0].closed
    assert pair.sessions[0]._handler_tasks == set()
    assert pair.sessions[0]._pending == {}
    assert pair.managers[0]._turn_waiters == {}
    assert pair.hubs[0] == {}
    await pair.managers[1].disconnect("conn")
    await pair.managers[0].disconnect("conn")
    with pytest.raises(ConnectionError, match="bridge session closed"):
        await asyncio.wait_for(pair.turns[1], timeout=2)
    assert pair.sessions[1]._handler_tasks == set()
    assert pair.managers[1]._turn_waiters == {}
    assert pair.hubs[1] == {}


@pytest.mark.asyncio
async def test_tunnel_errors_still_reply_and_failed_handlers_are_observed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    frames: list[dict[str, Any]] = []

    async def send(text: str) -> None:
        frames.append(json.loads(text))

    async def fail_tunnel(_payload: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("invalid request")

    async def fail_turn(_payload: dict[str, Any]) -> None:
        raise ValueError("failed turn")

    session = BridgeSession(
        connection_id="conn",
        send_text=send,
        on_tunnel_request=fail_tunnel,
        on_turn_frame=fail_turn,
    )
    await session.handle_message(json.dumps({"type": "tunnel.request", "id": "request"}))
    await session.handle_message(json.dumps({"type": "turn.start", "request_id": "turn"}))
    tasks = list(session._handler_tasks)
    await asyncio.gather(*tasks, return_exceptions=True)
    assert frames == [
        {
            "type": "tunnel.error",
            "id": "request",
            "code": "TUNNEL_ERROR",
            "message": "invalid request",
        }
    ]
    assert "handler failed" in caplog.text
    assert "failed turn" in caplog.text
    assert session._handler_tasks == set()
    await session.close()


@pytest.mark.asyncio
async def test_handler_can_close_its_session_and_reenter_close_during_cleanup() -> None:
    closing = asyncio.Event()
    waiting = asyncio.Event()
    cleaned = asyncio.Event()

    async def send(_text: str) -> None:
        pass

    async def handler(payload: dict[str, Any]) -> None:
        if payload["request_id"] == "close":
            await waiting.wait()
            await session.close()
            closing.set()
        else:
            waiting.set()
            try:
                await asyncio.Event().wait()
            finally:
                await session.close()
                cleaned.set()

    session = BridgeSession(connection_id="conn", send_text=send, on_turn_frame=handler)
    try:
        for request_id in ("wait", "close"):
            await session.handle_message(
                json.dumps({"type": "turn.start", "request_id": request_id})
            )
        await asyncio.wait_for(closing.wait(), timeout=2)
        await asyncio.gather(*session._handler_tasks, return_exceptions=True)
        # The closing handler's done callback runs on the next loop iteration.
        await asyncio.sleep(0)
        assert cleaned.is_set()
        assert session.closed
        assert session._handler_tasks == set()
    finally:
        await session.close()
