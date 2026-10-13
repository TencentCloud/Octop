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
    """Validate a peer ``turn.start`` and build the gateway inbound."""
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
    inbound = build_dashboard_inbound(
        agent_id=agent_id,
        user_id=user.id,
        prepared=prepared,
        turn=turn,
        ws_connection_id=ws_connection_id,
        user_is_admin=bool(getattr(user, "is_admin", False)),
    )
    return PreparedPeerTurn(thread_id=prepared.thread_id, inbound=inbound)
