"""Peer-turn payload keys, runner protocols, and rejection types (no ``api/`` imports)."""

from __future__ import annotations

from typing import Any, Protocol

# Keep in sync with ``UserTurnWsFrame`` in ``octop.api.routers.chat.models``.
# tests/unit/bridge/test_peer_turn.py asserts the two stay aligned.
USER_TURN_WS_KEYS = frozenset(
    {
        "text",
        "session_key",
        "thread_id",
        "model",
        "default_model",
        "reasoning_mode",
        "reasoning_effort",
        "conversation_mode",
        "hitl_policy",
        "mcp_servers",
        "knowledge_base_ids",
        "skills",
        "messages",
        "target_agent_ids",
    }
)


class PeerTurnRejected(ValueError):
    """Peer turn was syntactically fine but must not be enqueued."""


class PreparedPeerTurnLike(Protocol):
    thread_id: str
    inbound: Any


class PeerTurnRunner(Protocol):
    async def __call__(
        self,
        *,
        server: Any,
        user: Any,
        agent_id: str,
        payload: dict[str, Any],
        ws_connection_id: str,
    ) -> PreparedPeerTurnLike: ...


class PeerBrowserRunner(Protocol):
    async def __call__(
        self,
        *,
        send_json: Any,
        is_connected: Any,
        receive_text: Any,
        user_id: int,
        listen_only: bool = ...,
        default_width: int = ...,
        default_height: int = ...,
        start_msg: dict[str, Any] | None = ...,
    ) -> None: ...


def bridge_turn_ws_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Copy dashboard turn fields off a ``turn.start`` frame.

    Hub relays the full ``user_turn`` body; dropping keys here would silently
    ignore knowledge bases, HITL policy, and conversation mode.
    """
    out = {key: value for key, value in payload.items() if key in USER_TURN_WS_KEYS}
    out["type"] = "user_turn"
    out.setdefault("text", payload.get("text") or "")
    return out
