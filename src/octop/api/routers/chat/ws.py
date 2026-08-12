"""Dashboard chat over WebSocket — routes turns through Gateway / GlobalProcessor."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from octop.api.common.agent import assert_agent_access
from octop.api.deps import resolve_user_from_token
from octop.api.routers.chat.models import UserTurnWsFrame
from octop.api.routers.chat.sse import json_chunk_default
from octop.api.routers.chat.turn import (
    build_dashboard_inbound,
    prepare_dashboard_turn,
    turn_has_content,
)
from octop.infra.errors import OctopError
from octop.infra.gateway.ws import WS_CHANNEL_ID

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/agents/{agent_id}/chat/ws")
async def dashboard_chat_ws(
    websocket: WebSocket,
    agent_id: str,
    token: str | None = Query(default=None),
) -> None:
    """Bidirectional Dashboard chat. Wire protocol mirrors harness stream chunks."""
    server = websocket.app.state.octop_server
    if not token:
        await websocket.close(code=4001, reason="missing token")
        return

    try:
        user = resolve_user_from_token(server, token)
    except OctopError as exc:
        await websocket.close(code=4001, reason=f"auth: {exc.code.value}")
        return

    assert server.app_runtime is not None  # noqa: S101
    gateway = server.app_runtime.gateway
    hub = gateway.ws_hub
    channel_manager = gateway.channel_manager
    if channel_manager is None:
        await websocket.close(code=1011, reason="gateway not ready")
        return

    try:
        assert_agent_access(server, agent_id, user)
    except OctopError as exc:
        from octop.infra.errors import ErrorCode  # noqa: PLC0415

        code = 4003 if exc.code == ErrorCode.FORBIDDEN else 4404
        await websocket.close(code=code, reason=str(exc.code.value))
        return

    connection_id = uuid.uuid4().hex
    await websocket.accept()

    # The harness/gateway workers run on the server event loop, but this
    # handler may run on a different loop (e.g. starlette's TestClient portal).
    # Marshal outbound frames onto the loop that owns this WebSocket so
    # cross-loop sends don't deadlock.
    ws_loop = asyncio.get_running_loop()

    async def _emit_frame(frame: dict[str, Any]) -> None:
        if websocket.application_state != WebSocketState.CONNECTED:
            return
        await websocket.send_text(
            json.dumps(frame, ensure_ascii=False, default=json_chunk_default),
        )

    async def send_frame(frame: dict[str, Any]) -> None:
        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(_emit_frame(frame), ws_loop))

    hub.register(connection_id, send_frame)

    try:
        while websocket.application_state == WebSocketState.CONNECTED:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"type": "user_turn", "text": raw}

            if not isinstance(payload, dict):
                continue

            msg_type = str(payload.get("type") or "user_turn")
            if msg_type == "ping":
                await send_frame({"type": "pong"})
                continue

            if msg_type == "subscribe":
                thread_id = str(payload.get("thread_id") or "").strip()
                if not thread_id:
                    await send_frame({"type": "error", "message": "subscribe requires thread_id"})
                    continue
                row = gateway.thread_registry.get_thread(thread_id)
                if row is None or row.agent_id != agent_id or row.user_id != user.id:
                    await send_frame(
                        {"type": "error", "message": f"thread {thread_id!r} not found"},
                    )
                    continue
                hub.subscribe(thread_id, connection_id)
                await send_frame(
                    {
                        "type": "turn_status",
                        "thread_id": thread_id,
                        "active": hub.is_turn_active(thread_id),
                    },
                )
                continue

            if msg_type == "cancel":
                thread_id = str(payload.get("thread_id") or "").strip()
                if not thread_id:
                    await send_frame({"type": "error", "message": "cancel requires thread_id"})
                    continue
                row = gateway.thread_registry.get_thread(thread_id)
                if row is None or row.agent_id != agent_id or row.user_id != user.id:
                    await send_frame(
                        {"type": "error", "message": f"thread {thread_id!r} not found"},
                    )
                    continue
                server.app_runtime.agent_registry.cancel_stream(agent_id, thread_id)
                continue

            if msg_type != "user_turn":
                await send_frame({"type": "error", "message": f"unknown message type: {msg_type}"})
                continue

            try:
                frame = UserTurnWsFrame.model_validate({**payload, "type": "user_turn"})
            except ValidationError as exc:
                await send_frame({"type": "error", "message": str(exc)})
                await send_frame({"type": "done"})
                continue

            turn = frame.to_turn_body()
            if not turn_has_content(turn):
                await send_frame({"type": "error", "message": "empty message"})
                await send_frame({"type": "done"})
                continue

            try:
                prepared = await prepare_dashboard_turn(
                    server,
                    agent_id=agent_id,
                    user=user,
                    turn=turn,
                )
            except OctopError as exc:
                await send_frame({"type": "error", "message": str(exc)})
                await send_frame({"type": "done"})
                continue

            inbound = build_dashboard_inbound(
                agent_id=agent_id,
                user_id=user.id,
                prepared=prepared,
                turn=turn,
                ws_connection_id=connection_id,
                user_is_admin=bool(getattr(user, "is_admin", False)),
            )
            hub.subscribe(prepared.thread_id, connection_id)
            channel_manager.enqueue(WS_CHANNEL_ID, inbound)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("dashboard chat ws error agent=%s", agent_id)
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await send_frame({"type": "error", "message": "internal error"})
    finally:
        # Disconnect must not cancel an in-flight turn — clients may reconnect and
        # subscribe to continue receiving subsequent chunks (weak stream resume).
        hub.unregister(connection_id)
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()
