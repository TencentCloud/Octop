"""ASGI-layer helpers that Bridge calls for local dashboard turns.

Wired from ``build_app`` so ``infra.bridge`` never imports ``api/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from octop.api.routers.chat.models import UserTurnWsFrame
from octop.api.routers.chat.turn import (
    build_dashboard_inbound,
    prepare_dashboard_turn,
    turn_has_content,
)
from octop.infra.bridge.peer_turn import PeerTurnRejected, bridge_turn_ws_payload


@dataclass(frozen=True)
class PreparedPeerTurn:
    thread_id: str
    inbound: Any


async def prepare_peer_dashboard_turn(
    *,
    server: Any,
    user: Any,
    agent_id: str,
    payload: dict[str, Any],
    ws_connection_id: str,
) -> PreparedPeerTurn:
    """Validate a peer ``turn.start`` and build the gateway inbound.

    When the room is already busy, admit a mid-turn steer and return
    ``inbound=None`` so the peer does not enqueue a second turn.
    """
    frame = UserTurnWsFrame.model_validate(bridge_turn_ws_payload(payload))
    turn = frame.to_turn_body()
    if not turn_has_content(turn):
        raise PeerTurnRejected("empty message")
    prepared = await prepare_dashboard_turn(
        server,
        agent_id=agent_id,
        user=user,
        turn=turn,
    )
    if await _admit_peer_steer(
        server,
        agent_id=agent_id,
        thread_id=prepared.thread_id,
        turn=turn,
    ):
        return PreparedPeerTurn(thread_id=prepared.thread_id, inbound=None)
    inbound = build_dashboard_inbound(
        agent_id=agent_id,
        user_id=user.id,
        prepared=prepared,
        turn=turn,
        ws_connection_id=ws_connection_id,
        user_is_admin=bool(getattr(user, "is_admin", False)),
    )
    return PreparedPeerTurn(thread_id=prepared.thread_id, inbound=inbound)


async def _admit_peer_steer(
    server: Any,
    *,
    agent_id: str,
    thread_id: str,
    turn: Any,
) -> bool:
    """Push steer.ack / queued onto the live turn subscriber when busy."""
    rt = getattr(server, "app_runtime", None)
    gateway = getattr(rt, "gateway", None) if rt is not None else None
    if gateway is None:
        return False
    from octop.api.routers.chat.ws import (  # noqa: PLC0415
        _maybe_admit_steer,
        _plain_text_from_turn,
        _steer_blocks_from_turn,
        _thread_hitl_paused,
    )

    hub = gateway.ws_hub
    delivery = turn.delivery or "auto"
    # Team members speak after the host WS turn goes idle. A leftover steer
    # coordinator row must not swallow the next user_turn as a queued insert.
    if (
        delivery != "steer"
        and not hub.is_turn_active(thread_id)
        and not _thread_hitl_paused(gateway, thread_id, agent_id)
    ):
        return False

    async def send_via_hub(steer_frame: dict[str, Any]) -> None:
        await hub.push_to_thread(thread_id, steer_frame)

    return await _maybe_admit_steer(
        text=(turn.text or "").strip() or _plain_text_from_turn(turn),
        thread_id=thread_id,
        delivery=delivery,
        client_pending_id=turn.client_pending_id,
        expected_turn_id=turn.expected_turn_id,
        steer=gateway.steer,
        hub=hub,
        send_frame=send_via_hub,
        hitl_paused=_thread_hitl_paused(gateway, thread_id, agent_id),
        content_blocks=_steer_blocks_from_turn(turn),
    )
