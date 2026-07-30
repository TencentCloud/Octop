"""Derive session keys and user ids from harness-gateway InboundMessage."""

from __future__ import annotations

from typing import Any

from harness_gateway.models import ImageContent, InboundMessage

from octop.infra.gateway.threads import ThreadRegistry

# Persisted on HumanMessage.additional_kwargs for dashboard history UI.
COMPOSER_CTX_KEY = "octop_composer_context"
INBOUND_ATTACHMENTS_KEY = "octop_inbound_attachments"


def build_composer_context(
    *,
    mcp_servers: list[str] | None,
    skills: list[str] | None,
    target_agent_ids: list[str] | None,
    model_ref: str | None,
    default_model: str | None,
) -> dict[str, Any] | None:
    """Snapshot of per-turn composer selections for history display chips.

    Shared by dashboard chat and cron agent runs so MessageBubble can render
    connector / skill / model tags the same way.

    Only stamped on newly written HumanMessages — existing history is not
    backfilled when job/chat settings change.
    """
    ctx: dict[str, Any] = {}
    if mcp_servers:
        ctx["connectors"] = list(mcp_servers)
    if skills:
        ctx["skills"] = list(skills)
    if target_agent_ids:
        ctx["targetAgents"] = [str(x) for x in target_agent_ids]
    model = (model_ref or "").strip()
    default = (default_model or "").strip()
    if model and model != default:
        ctx["model"] = model
    return ctx or None


try:
    from harness_gateway.push_routing import EPHEMERAL_PUSH_META
except ImportError:  # pragma: no cover - older harness-gateway
    EPHEMERAL_PUSH_META = frozenset(
        {
            "msg_id",
            "message_id",
            "_frame",
            "_ws_client",
            "response_url",
            "context_token",
            "webhook_url",
        },
    )


def user_id_from_message(msg: InboundMessage) -> int:
    """Legacy helper — prefer :func:`resolve_user_id_for_message`."""
    return resolve_user_id_for_message(msg, agent_owner_id=None)


def resolve_user_id_for_message(
    msg: InboundMessage,
    *,
    agent_owner_id: int | None,
) -> int:
    """Resolve Octop ``users.id`` for thread/session persistence.

    Dashboard WS uses numeric ``subject_id`` (Octop user id). IM platforms
    (QQ openid, WeCom userid, …) use opaque strings — those cannot satisfy
    ``threads.user_id`` FK as ``0``; fall back to the agent owner instead.
    """
    sid = subject_id_from_message(msg)
    try:
        uid = int(sid)
        if uid > 0:
            return uid
    except (ValueError, TypeError):
        pass
    if agent_owner_id is not None and agent_owner_id > 0:
        return agent_owner_id
    return 0


def subject_id_from_message(msg: InboundMessage) -> str:
    if msg.channel_subject and msg.channel_subject.subject_id:
        return msg.channel_subject.subject_id
    return "0"


def chat_type_from_message(msg: InboundMessage) -> str:
    meta = msg.metadata or {}
    ct = meta.get("chat_type")
    if ct in (ThreadRegistry.CHAT_TYPE_DM, ThreadRegistry.CHAT_TYPE_GROUP):
        return str(ct)
    if meta.get("chat_type") == "group" or meta.get("is_group"):
        return ThreadRegistry.CHAT_TYPE_GROUP
    return ThreadRegistry.CHAT_TYPE_DM


def session_key_from_message(msg: InboundMessage, *, agent_id: str) -> str:
    meta = msg.metadata or {}
    explicit = meta.get("session_key")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return ThreadRegistry.make_key(
        agent_id=agent_id,
        channel_type=msg.channel_type or "unknown",
        channel_subject_id=subject_id_from_message(msg),
        channel_chat_type=chat_type_from_message(msg),
    )


def images_from_message(msg: InboundMessage) -> list[ImageContent]:
    return [part for part in msg.content if isinstance(part, ImageContent)]


_EPHEMERAL_SESSION_META = EPHEMERAL_PUSH_META
EPHEMERAL_IM_META = _EPHEMERAL_SESSION_META
_PERSISTED_META_KEYS = (
    "msg_type",
    "message_type",
    "chat_type",
    "chat_id",
    "chatid",
    "user_openid",
    "group_openid",
    "to_handle",
    "event_type",
    "guild_id",
    "channel_id_native",
    "group_id",
    "account_id",
    "from_user_id",
    "ilink_user_id",
    "ws_connection_id",
    "session_id",
    "task_id",
)


def sanitize_im_metadata(msg: InboundMessage) -> dict[str, object]:
    """Extract durable IM routing fields from an inbound message for session storage.

    Persists fields needed for proactive push (msg_type, openids, chat_id, …).
    Strips ephemeral passive-reply context (msg_id, response_url, _frame, …).
    """
    raw = dict(msg.metadata or {})
    out: dict[str, object] = {}
    for key in _PERSISTED_META_KEYS:
        if key in raw and raw[key] not in (None, ""):
            out[key] = raw[key]
    if "chatid" in out and "chat_id" not in out:
        out["chat_id"] = out.pop("chatid")
    chat_type = out.get("chat_type")
    if chat_type == "single":
        out["chat_type"] = ThreadRegistry.CHAT_TYPE_DM
    for key in _EPHEMERAL_SESSION_META:
        out.pop(key, None)
    out.setdefault("channel_type", msg.channel_type or "unknown")
    return out
