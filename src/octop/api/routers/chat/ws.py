"""Dashboard chat over WebSocket — routes turns through Gateway / GlobalProcessor."""

from __future__ import annotations

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
from octop.infra.bridge.ids import parse_bridge_agent_id
from octop.infra.errors import OctopError
from octop.infra.gateway.steer import SteerAdmitOk, SteerAdmitReject, SteerCoordinator
from octop.infra.gateway.steer.types import preview_text
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

    bridge_ref = parse_bridge_agent_id(agent_id)
    if bridge_ref is not None:
        await _bridge_chat_ws(websocket, server=server, user=user, ref=bridge_ref)
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

    async def send_frame(frame: dict[str, Any]) -> None:
        if websocket.application_state != WebSocketState.CONNECTED:
            return
        await websocket.send_text(
            json.dumps(frame, ensure_ascii=False, default=json_chunk_default),
        )

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
                for frame in gateway.steer.snapshot_frames(thread_id):
                    await send_frame({**frame, "thread_id": thread_id})
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
                gateway.steer.mark_cancelling(thread_id)
                discarded = gateway.steer.discard(thread_id, reason="turn_cancelled")
                if discarded is not None:
                    await hub.push_to_thread(
                        thread_id,
                        {
                            "type": "steer.discarded",
                            "seq": discarded.seq,
                            "client_pending_ids": discarded.client_pending_ids,
                            "pending_ids": discarded.pending_ids,
                            "turn_id": discarded.turn_id,
                            "reason": discarded.reason,
                            "thread_id": thread_id,
                        },
                    )
                server.app_runtime.agent_registry.cancel_stream(agent_id, thread_id)
                continue

            if msg_type == "steer_remove":
                await _handle_steer_remove(
                    payload,
                    gateway=gateway,
                    hub=hub,
                    send_frame=send_frame,
                    agent_id=agent_id,
                    user_id=user.id,
                )
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
            # Resolve thread early so busy routing can run before prepare.
            try:
                prepared_early = await prepare_dashboard_turn(
                    server,
                    agent_id=agent_id,
                    user=user,
                    turn=turn,
                )
            except OctopError as exc:
                await send_frame({"type": "error", "message": str(exc)})
                await send_frame({"type": "done"})
                continue

            steered = await _maybe_admit_steer(
                text=(turn.text or "").strip() or _plain_text_from_turn(turn),
                thread_id=prepared_early.thread_id,
                delivery=turn.delivery or "auto",
                client_pending_id=turn.client_pending_id,
                expected_turn_id=turn.expected_turn_id,
                steer=gateway.steer,
                hub=hub,
                send_frame=send_frame,
                hitl_paused=_thread_hitl_paused(gateway, prepared_early.thread_id, agent_id),
            )
            if steered:
                continue

            if not turn_has_content(turn):
                await send_frame({"type": "error", "message": "empty message"})
                await send_frame({"type": "done"})
                continue

            inbound = build_dashboard_inbound(
                agent_id=agent_id,
                user_id=user.id,
                prepared=prepared_early,
                turn=turn,
                ws_connection_id=connection_id,
                user_is_admin=bool(getattr(user, "is_admin", False)),
            )
            hub.subscribe(prepared_early.thread_id, connection_id)
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


async def _bridge_chat_ws(
    websocket: WebSocket,
    *,
    server: Any,
    user: Any,
    ref: Any,
) -> None:
    """Relay dashboard chat frames to a remote agent over Bridge WS."""
    rt = server.app_runtime
    mgr = getattr(rt, "bridge_manager", None) if rt is not None else None
    if mgr is None:
        await websocket.close(code=1011, reason="bridge not ready")
        return
    try:
        mgr.get_owned(ref.connection_id, user.id)
        mgr.require_session(ref.connection_id)
    except OctopError as exc:
        await websocket.close(code=1011, reason=str(exc.code.value))
        return

    await websocket.accept()

    async def send_frame(frame: dict[str, Any]) -> None:
        if websocket.application_state != WebSocketState.CONNECTED:
            return
        await websocket.send_text(
            json.dumps(frame, ensure_ascii=False, default=json_chunk_default),
        )

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
                # History/live resume stays on the peer; acknowledge without local hub.
                thread_id = str(payload.get("thread_id") or "").strip()
                await send_frame(
                    {
                        "type": "turn_status",
                        "thread_id": thread_id,
                        "active": False,
                    }
                )
                continue
            if msg_type == "cancel":
                await send_frame({"type": "error", "message": "cancel not supported on bridge yet"})
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
            turn_payload = frame.model_dump(exclude_none=True)
            turn_payload.pop("type", None)
            try:
                await mgr.relay_user_turn(
                    connection_id=ref.connection_id,
                    owner_user_id=user.id,
                    remote_agent_id=ref.remote_agent_id,
                    turn_payload=turn_payload,
                    on_frame=send_frame,
                )
            except OctopError as exc:
                await send_frame({"type": "error", "message": str(exc)})
                await send_frame({"type": "done"})
            except Exception:
                logger.exception("bridge chat relay failed")
                await send_frame({"type": "error", "message": "bridge turn failed"})
                await send_frame({"type": "done"})
    except WebSocketDisconnect:
        pass
    finally:
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()


def _plain_text_from_turn(turn: Any) -> str:
    text = (getattr(turn, "text", None) or "").strip()
    if text:
        return text
    messages = getattr(turn, "messages", None) or []
    if not messages:
        return ""
    last = messages[-1]
    if not isinstance(last, dict):
        return ""
    content = last.get("content")
    if isinstance(content, str):
        return content.strip()
    return ""


def _thread_hitl_paused(gateway: Any, thread_id: str, agent_id: str) -> bool:
    processor = getattr(gateway, "processor", None)
    hitl = getattr(processor, "hitl_coordinator", None) if processor is not None else None
    store = getattr(hitl, "store", None) if hitl is not None else None
    resolve = getattr(store, "resolve_pending_for_thread", None)
    if resolve is None:
        return False
    try:
        return resolve(thread_id, agent_id=agent_id) is not None
    except Exception:
        logger.exception("hitl pause probe failed thread=%s", thread_id)
        return False


async def _maybe_admit_steer(
    *,
    text: str,
    thread_id: str,
    delivery: str,
    client_pending_id: str | None,
    expected_turn_id: str | None,
    steer: SteerCoordinator,
    hub: Any,
    send_frame: Any,
    hitl_paused: bool,
) -> bool:
    """Return True when the frame was handled as a steer (queued/rejected/idle-bypass False)."""
    if delivery not in ("auto", "steer", "follow_up"):
        delivery = "auto"
    if not steer.is_active(thread_id) and delivery != "steer" and delivery != "follow_up":
        return False
    if not steer.is_active(thread_id) and delivery == "follow_up":
        return False

    result = steer.admit(
        thread_id,
        text=text,
        client_pending_id=client_pending_id,
        expected_turn_id=expected_turn_id,
        delivery=delivery,  # type: ignore[arg-type]
        hitl_paused=hitl_paused,
    )
    if result is None:
        return False

    if isinstance(result, SteerAdmitReject):
        # Never emit type=error here — that frame lands on the live turn
        # socket and the Dashboard treats it as a stream failure bubble
        # (``client_pending_id_required`` / expected_turn_id_*).
        await hub.push_to_thread(
            thread_id,
            {
                "type": "steer.rejected",
                "seq": result.seq,
                "client_pending_id": result.client_pending_id,
                "reason": result.reason,
                "active_turn_id": result.turn_id,
                "thread_id": thread_id,
                "gateway_class": bool(
                    result.gateway_class or SteerCoordinator.is_gateway_reason(result.reason)
                ),
            },
        )
        await send_frame(
            {
                "type": "steer.ack",
                "status": "rejected",
                "reason": result.reason,
                "client_pending_id": result.client_pending_id,
                "turn_id": result.turn_id,
                "thread_id": thread_id,
            }
        )
        return True

    if not isinstance(result, SteerAdmitOk):  # pragma: no cover - defensive
        raise TypeError(f"unexpected steer admit result: {result!r}")
    await send_frame(
        {
            "type": "steer.ack",
            "status": result.status,
            "turn_id": result.turn_id,
            "pending_id": result.pending_id,
            "client_pending_id": result.client_pending_id,
            "message_id": result.message_id,
            "thread_id": thread_id,
        }
    )
    if result.emit_queued and result.seq is not None:
        await hub.push_to_thread(
            thread_id,
            {
                "type": "steer.queued",
                "seq": result.seq,
                "client_pending_id": result.client_pending_id,
                "pending_id": result.pending_id,
                "turn_id": result.turn_id,
                "queue_length": result.queue_length,
                "preview": preview_text(text),
                "thread_id": thread_id,
            },
        )
    return True


async def _handle_steer_remove(
    payload: dict[str, Any],
    *,
    gateway: Any,
    hub: Any,
    send_frame: Any,
    agent_id: str,
    user_id: int,
) -> None:
    thread_id = str(payload.get("thread_id") or "").strip()
    turn_id = str(payload.get("turn_id") or "").strip()
    client_pending_id = str(payload.get("client_pending_id") or "").strip()
    pending_id = str(payload.get("pending_id") or "").strip()
    if not thread_id or not turn_id:
        await send_frame(
            {"type": "error", "message": "steer_remove requires thread_id and turn_id"}
        )
        return
    row = gateway.thread_registry.get_thread(thread_id)
    if row is None or row.agent_id != agent_id or row.user_id != user_id:
        await send_frame({"type": "error", "reason": "forbidden", "message": "forbidden"})
        return
    if not client_pending_id or not pending_id:
        await send_frame(
            {
                "type": "error",
                "reason": "client_pending_id_required",
                "client_pending_id": client_pending_id or None,
                "message": "client_pending_id_required",
            }
        )
        return
    result = gateway.steer.remove(
        thread_id,
        turn_id=turn_id,
        client_pending_id=client_pending_id,
        pending_id=pending_id,
    )
    await send_frame(
        {
            "type": "steer.ack",
            "status": "removed",
            "turn_id": result.turn_id,
            "pending_id": result.pending_id,
            "client_pending_id": result.client_pending_id,
            "already_drained": result.already_drained or None,
            "already_gone": result.already_gone or None,
            "thread_id": thread_id,
        }
    )
    if result.emit_removed and result.seq is not None:
        await hub.push_to_thread(
            thread_id,
            {
                "type": "steer.removed",
                "seq": result.seq,
                "client_pending_id": result.client_pending_id,
                "pending_id": result.pending_id,
                "turn_id": result.turn_id,
                "already_drained": result.already_drained or None,
                "already_gone": result.already_gone or None,
                "thread_id": thread_id,
            },
        )
