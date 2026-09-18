"""Per-invocation identity facts from gateway adapters, separate from Octop ownership."""

from __future__ import annotations

from typing import TypedDict

from harness_gateway.models import InboundMessage

from octop.infra.gateway.process.message_keys import chat_type_from_message
from octop.infra.utils.locale import Locale, normalize_locale

INBOUND_CONTEXT_KEY = "octop_inbound_context"


class InboundSender(TypedDict):
    namespace: str
    id: str


class InboundContext(TypedDict):
    channel_type: str
    channel_id: str
    octop_user_id: int
    sender: InboundSender | None
    chat_type: str
    conversation_id: str | None
    message_id: str | None
    locale: Locale


def _identifier(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value if value and value.lower() != "unknown" else None


def build_inbound_context(
    msg: InboundMessage, *, user_id: int, locale: str | Locale
) -> InboundContext:
    """Project only identity/routing fields, never raw frames or reply credentials.

    WeCom's adapter derives both ``to_handle`` and subject from ``from.userid``.
    Require those fields to agree; the Octop owner, body and session key are
    not substitutes for a missing platform identity. Other channel adapters
    need their own sender contract before populating ``sender`` here.
    """
    meta = msg.metadata or {}
    channel_type = msg.channel_type or "unknown"
    subject_id = _identifier(msg.channel_subject.subject_id) if msg.channel_subject else None
    chat_type = chat_type_from_message(msg)
    sender: InboundSender | None = None
    if channel_type == "wecom" and msg.channel_id:
        sender_id = _identifier(meta.get("to_handle"))
        if sender_id is not None and sender_id == subject_id:
            sender = {"namespace": f"wecom:{msg.channel_id}", "id": sender_id}

    return {
        "channel_type": channel_type,
        "channel_id": msg.channel_id,
        "octop_user_id": user_id,
        "sender": sender,
        "chat_type": chat_type,
        "conversation_id": _identifier(meta.get("chat_id"))
        or (subject_id if chat_type == "dm" else None),
        "message_id": _identifier(meta.get("msgid")),
        "locale": normalize_locale(locale),
    }
