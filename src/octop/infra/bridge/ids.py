"""Bridge remote agent id helpers: ``bridge:{connection_id}:{remote_agent_id}``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

BRIDGE_AGENT_PREFIX = "bridge:"
_BRIDGE_PROTOCOL_VERSION = 1

PROTOCOL_VERSION = _BRIDGE_PROTOCOL_VERSION


@dataclass(frozen=True)
class BridgeAgentRef:
    connection_id: str
    remote_agent_id: str

    @property
    def agent_id(self) -> str:
        return format_bridge_agent_id(self.connection_id, self.remote_agent_id)


def format_bridge_agent_id(connection_id: str, remote_agent_id: str) -> str:
    cid = connection_id.strip()
    aid = remote_agent_id.strip()
    if not cid or not aid:
        raise ValueError("connection_id and remote_agent_id required")
    if ":" in cid:
        raise ValueError("connection_id must not contain ':'")
    return f"{BRIDGE_AGENT_PREFIX}{cid}:{aid}"


def parse_bridge_agent_id(agent_id: str) -> BridgeAgentRef | None:
    raw = (agent_id or "").strip()
    if not raw.startswith(BRIDGE_AGENT_PREFIX):
        return None
    rest = raw[len(BRIDGE_AGENT_PREFIX) :]
    connection_id, sep, remote_agent_id = rest.partition(":")
    if not sep or not connection_id.strip() or not remote_agent_id.strip():
        return None
    return BridgeAgentRef(
        connection_id=connection_id.strip(),
        remote_agent_id=remote_agent_id.strip(),
    )


def is_bridge_agent_id(agent_id: str) -> bool:
    return parse_bridge_agent_id(agent_id) is not None


def rewrite_peer_agent_id(connection_id: str, peer_agent_id: str | None) -> str | None:
    """Map a peer-local agent id onto the local Bridge shadow id."""
    raw = (peer_agent_id or "").strip()
    if not raw:
        return None
    if is_bridge_agent_id(raw):
        return raw
    return format_bridge_agent_id(connection_id, raw)


def rewrite_peer_agent_ids(connection_id: str, ids: list[object]) -> list[str]:
    """Rewrite a roster of peer-local ids; skip blanks and duplicates."""
    out: list[str] = []
    seen: set[str] = set()
    for item in ids:
        mapped = rewrite_peer_agent_id(connection_id, str(item) if item is not None else None)
        if mapped is None or mapped in seen:
            continue
        seen.add(mapped)
        out.append(mapped)
    return out


def rewrite_peer_payload_agent_id(connection_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Rewrite ``agent_id`` on a peer stream/history payload onto the local shadow."""
    mapped = rewrite_peer_agent_id(
        connection_id,
        str(payload["agent_id"]) if payload.get("agent_id") is not None else None,
    )
    if mapped is None or mapped == payload.get("agent_id"):
        return payload
    out = dict(payload)
    out["agent_id"] = mapped
    return out


_TUNNEL_AGENT_ID_KEYS = frozenset(
    {
        "agent_id",
        "speaker_agent_id",
        "from_agent_id",
        "to_agent_id",
        "host_agent_id",
        "remote_agent_id",
    }
)
_TUNNEL_AGENT_ID_LIST_KEYS = frozenset({"member_ids", "target_agent_ids"})
_TUNNEL_URL_KEYS = frozenset({"icon_url", "icon", "url", "preview_url"})


def rewrite_agent_url_segment(text: str, *, remote_agent_id: str, bridge_agent_id: str) -> str:
    """Rewrite ``/api/agents/{peer}`` path segments onto the local shadow id."""
    raw = str(text or "")
    remote = (remote_agent_id or "").strip()
    shadow = (bridge_agent_id or "").strip()
    if not raw or not remote or not shadow:
        return raw
    out = raw
    for prefix in ("/api/agents/", "/api/plugins/agents/"):
        token = f"{prefix}{remote}"
        if token in out:
            out = out.replace(token, f"{prefix}{shadow}")
    return out


def rewrite_tunneled_json(
    payload: Any,
    *,
    remote_agent_id: str,
    bridge_agent_id: str,
) -> Any:
    """Rewrite agent identity fields in a tunneled JSON body.

    Do **not** substring-replace the peer agent id: team member threads are
    ``{room}~{member}`` and session keys start with ``{agent_id}:``. A blanket
    replace would make those ids unreadable on the peer.
    """
    remote = (remote_agent_id or "").strip()
    shadow = (bridge_agent_id or "").strip()
    if not remote or not shadow:
        return payload

    def walk(value: Any, key: str | None) -> Any:
        if isinstance(value, dict):
            return {k: walk(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(item, key) for item in value]
        if not isinstance(value, str):
            return value
        if (
            key in _TUNNEL_AGENT_ID_KEYS or key in _TUNNEL_AGENT_ID_LIST_KEYS
        ) and value.strip() == remote:
            return shadow
        if key in _TUNNEL_URL_KEYS:
            return rewrite_agent_url_segment(value, remote_agent_id=remote, bridge_agent_id=shadow)
        return value

    return walk(payload, None)


def restore_peer_path_ids(rest: str, *, bridge_agent_id: str, remote_agent_id: str) -> str:
    """Map a hub path suffix that embedded the shadow id back to the peer id.

    Lets a stale tab still load ``…/threads/{room}~bridge:cid:member/history``.
    """
    out = rest or ""
    shadow = (bridge_agent_id or "").strip()
    remote = (remote_agent_id or "").strip()
    if not out or not shadow or not remote or shadow not in out:
        return out
    return out.replace(shadow, remote)
