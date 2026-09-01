"""Dashboard-wide notification WebSocket — text pushes (cron / proactive care)."""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from octop.api.deps import resolve_user_from_token
from octop.api.routers.chat.sse import json_chunk_default
from octop.infra.errors import OctopError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/notifications/ws")
async def dashboard_notifications_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """Push ``dashboard_push`` frames to the signed-in user's dashboard clients."""
    server = websocket.app.state.octop_server
    if not token:
        await websocket.close(code=4001, reason="missing token")
        return

    try:
        user = resolve_user_from_token(server, token)
    except OctopError as exc:
        await websocket.close(code=4001, reason=f"auth: {exc.code.value}")
        return

    if server.app_runtime is None:
        await websocket.close(code=1011, reason="server not ready")
        return
    hub = server.app_runtime.gateway.ws_hub

    connection_id = uuid.uuid4().hex
    await websocket.accept()

    async def send_frame(frame: dict[str, Any]) -> None:
        if websocket.application_state != WebSocketState.CONNECTED:
            return
        await websocket.send_text(
            json.dumps(frame, ensure_ascii=False, default=json_chunk_default),
        )

    hub.register(connection_id, send_frame, user_id=user.id)

    try:
        while websocket.application_state == WebSocketState.CONNECTED:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if str(payload.get("type") or "") == "ping":
                await send_frame({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("dashboard notifications ws error user=%s", user.id)
    finally:
        hub.unregister(connection_id)
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()
