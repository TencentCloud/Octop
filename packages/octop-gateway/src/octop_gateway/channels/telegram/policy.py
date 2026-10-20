"""Pure Telegram admission and activation policy, evaluated before media retrieval."""

from __future__ import annotations

import re

from telegram import Message


def parse_id_list(value: object, *, allow_negative: bool = False) -> list[str]:
    """Normalize a CSV string or list/tuple of nonzero integer IDs.

    Empty strings and None mean no restriction. User IDs must be positive;
    chat allowlists can opt into negative IDs. Invalid values raise ValueError,
    including booleans, floats, and empty entries. Duplicates retain first order.
    """
    if value is None:
        return []
    if isinstance(value, str):
        if not value.strip():
            return []
        values: list[object] = list(value.split(","))
    elif isinstance(value, list | tuple):
        values = list(value)
    else:
        raise ValueError("Telegram IDs must be a CSV string or a list of integers")

    result: list[str] = []
    pattern = r"-?[0-9]+" if allow_negative else r"[0-9]+"
    for item in values:
        if isinstance(item, bool) or not isinstance(item, int | str):
            raise ValueError("Telegram IDs must be integers, not booleans or floats")
        text = str(item).strip()
        if not re.fullmatch(pattern, text) or int(text) == 0:
            raise ValueError(f"Invalid Telegram ID: {item!r}")
        normalized = str(int(text))
        if normalized not in result:
            result.append(normalized)
    return result


def should_accept_message(
    message: Message,
    *,
    bot_id: int | None,
    bot_username: str | None,
    activation: str,
    allowed_user_ids: list[str],
    allowed_chat_ids: list[str],
    allow_unaddressed_commands: bool = False,
) -> bool:
    """Apply allowlists, command ownership, and group activation without I/O.

    Private chats bypass group activation. A command addressed to another bot
    is rejected in every mode. Restricted group modes require a known bot
    identity; each trigger uses the corresponding ID or username when available.
    Anonymous group senders cannot satisfy a user allowlist.
    """
    chat = message.chat
    if chat.type not in ("private", "group", "supergroup"):
        return False
    if allowed_chat_ids and str(chat.id) not in allowed_chat_ids:
        return False
    if allowed_user_ids:
        if message.sender_chat is not None or message.from_user is None:
            return False
        if str(message.from_user.id) not in allowed_user_ids:
            return False

    text = (message.text or message.caption or "").strip()
    if not text and not any((message.photo, message.document, message.video, message.voice, message.audio)):
        return False

    username = (bot_username or "").lstrip("@").casefold()
    mentioned = False
    own_command = False
    bare_command = False
    for entities, parse in (
        (message.entities, message.parse_entity),
        (message.caption_entities, message.parse_caption_entity),
    ):
        for entity in entities:
            if entity.type == "text_mention":
                if bot_id is not None and entity.user is not None and entity.user.id == bot_id:
                    mentioned = True
            elif entity.type in ("mention", "bot_command"):
                token = parse(entity)
                if entity.type == "mention":
                    if username and token.casefold() == f"@{username}":
                        mentioned = True
                elif "@" in token:
                    target = token.partition("@")[2].casefold()
                    if not username or target != username:
                        return False
                    own_command = True
                else:
                    bare_command = True

    if chat.type == "private":
        return True
    if activation == "always":
        return True
    if activation not in ("mention", "mention_or_reply") or (bot_id is None and not username):
        return False
    if mentioned or own_command or (bare_command and allow_unaddressed_commands):
        return True
    reply = message.reply_to_message
    return (
        activation == "mention_or_reply"
        and bot_id is not None
        and reply is not None
        and reply.sender_chat is None
        and reply.from_user is not None
        and reply.from_user.id == bot_id
    )
