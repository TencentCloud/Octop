"""Offline activation tests using real Telegram SDK messages and UTF-16 entities."""

from __future__ import annotations

from typing import Any

import pytest
from telegram import Message, MessageEntity

from octop_gateway.channels.telegram.policy import parse_id_list, should_accept_message


def message(*, text: str | None = "hello", chat_type: str = "supergroup", **fields: Any) -> Message:
    """Build SDK objects without a Bot or any network access."""
    data = {
        "message_id": 1,
        "date": 0,
        "chat": {"id": 42 if chat_type == "private" else -10042, "type": chat_type},
        "from": {"id": 7, "first_name": "User", "is_bot": False},
        "text": text,
        **fields,
    }
    result = Message.de_json(data, None)
    assert result is not None
    return result


def entity(text: str, token: str, kind: str = "mention", **fields: Any) -> dict[str, Any]:
    """Compute Telegram offsets in UTF-16 code units, including astral emoji."""
    return {
        "type": kind,
        "offset": len(text[: text.index(token)].encode("utf-16-le")) // 2,
        "length": len(token.encode("utf-16-le")) // 2,
        **fields,
    }


def accepts(msg: Message, **options: Any) -> bool:
    settings: dict[str, Any] = {
        "bot_id": 99,
        "bot_username": "Our_Bot",
        "activation": "mention_or_reply",
        "allowed_user_ids": [],
        "allowed_chat_ids": [],
    }
    return should_accept_message(msg, **(settings | options))


@pytest.mark.parametrize(
    ("value", "negative", "expected"),
    [
        (None, False, []),
        ("", False, []),
        (" 7, 8,7 ", False, ["7", "8"]),
        ([7, "008", " 9 "], False, ["7", "8", "9"]),
        ((7, "8"), False, ["7", "8"]),
        ("-10042,42", True, ["-10042", "42"]),
        ([-10042, "-43"], True, ["-10042", "-43"]),
    ],
)
def test_parse_id_list(value: Any, negative: bool, expected: list[str]) -> None:
    assert parse_id_list(value, allow_negative=negative) == expected


@pytest.mark.parametrize(
    "value",
    [True, False, 7, 1.5, {}, [True], [False], [1.0], [None], [""], "0", "-1", "1.5", "abc", "1,,2", "1,", "+7", "７"],
)
def test_invalid_id_list(value: Any) -> None:
    with pytest.raises(ValueError):
        parse_id_list(value)


@pytest.mark.parametrize("value", [True, [False], [0], "-0", "--7", "-1.5"])
def test_negative_ids_still_require_nonzero_integers(value: Any) -> None:
    with pytest.raises(ValueError):
        parse_id_list(value, allow_negative=True)


@pytest.mark.parametrize("chat_type", ["group", "supergroup"])
@pytest.mark.parametrize("activation", ["always", "mention", "mention_or_reply"])
def test_plain_group_activation(chat_type: str, activation: str) -> None:
    assert accepts(message(chat_type=chat_type), activation=activation) == (activation == "always")


@pytest.mark.parametrize("activation", ["always", "mention", "mention_or_reply"])
def test_private_bypasses_activation_but_checks_allowlists(activation: str) -> None:
    msg = message(chat_type="private")
    assert accepts(msg, activation=activation, bot_id=None, bot_username=None)
    assert accepts(msg, activation=activation, allowed_user_ids=["7"], allowed_chat_ids=["42"])
    assert not accepts(msg, activation=activation, allowed_user_ids=["8"])
    assert not accepts(msg, activation=activation, allowed_chat_ids=["-10042"])


@pytest.mark.parametrize("caption", [False, True])
@pytest.mark.parametrize("username,expected", [("@oUR_bOT", True), ("@other_bot", False), ("@Our_Bot_extra", False)])
def test_sdk_utf16_mentions(caption: bool, username: str, expected: bool) -> None:
    text = f"😀🧑 hello {username} please"
    item = entity(text, username)
    if caption:
        msg = message(
            text=None,
            caption=text,
            caption_entities=[item],
            photo=[{"file_id": "p", "file_unique_id": "p", "width": 1, "height": 1}],
        )
        assert msg.parse_caption_entity(msg.caption_entities[0]) == username
    else:
        msg = message(text=text, entities=[item])
        assert msg.parse_entity(msg.entities[0]) == username
    assert accepts(msg) is expected


@pytest.mark.parametrize("caption", [False, True])
@pytest.mark.parametrize("target,expected", [(99, True), (100, False)])
def test_text_mentions_match_id(caption: bool, target: int, expected: bool) -> None:
    text = "😀 hello Friendly Bot"
    item = entity(text, "Friendly Bot", "text_mention", user={"id": target, "first_name": "Bot", "is_bot": True})
    fields = {"caption": text, "caption_entities": [item]} if caption else {"entities": [item]}
    assert accepts(message(text=None if caption else text, **fields), bot_username=None) is expected


def test_plain_substrings_are_not_mentions() -> None:
    assert not accepts(message(text="hello @Our_Bot"))
    assert not accepts(message(text="@Our_Bot", entities=[entity("@Our_Bot", "@Our_Bot", "code")]))


@pytest.mark.parametrize("activation", ["always", "mention", "mention_or_reply"])
@pytest.mark.parametrize("target,expected", [("@OUR_bot", True), ("@other_bot", False), ("", False)])
@pytest.mark.parametrize("caption", [False, True])
def test_commands(activation: str, target: str, expected: bool, caption: bool) -> None:
    text = f"/help{target} details"
    item = entity(text, text.split()[0], "bot_command")
    fields = {"caption": text, "caption_entities": [item]} if caption else {"entities": [item]}
    msg = message(text=None if caption else text, **fields)
    assert accepts(msg, activation=activation) == (expected or (not target and activation == "always"))
    if not target:
        assert accepts(msg, activation=activation, allow_unaddressed_commands=True)


def test_other_bot_command_overrides_mention_and_reply() -> None:
    text = "/help@other_bot @Our_Bot"
    msg = message(
        text=text,
        entities=[entity(text, "/help@other_bot", "bot_command"), entity(text, "@Our_Bot")],
        reply_to_message={
            "message_id": 2,
            "date": 0,
            "chat": {"id": -10042, "type": "supergroup"},
            "from": {"id": 99, "first_name": "Bot", "is_bot": True},
            "text": "reply",
        },
    )
    for activation in ("always", "mention", "mention_or_reply"):
        assert not accepts(msg, activation=activation, allow_unaddressed_commands=True)


@pytest.mark.parametrize("activation", ["always", "mention", "mention_or_reply"])
@pytest.mark.parametrize("reply_id", [99, 100])
def test_reply_activation(activation: str, reply_id: int) -> None:
    reply = message(**{"from": {"id": reply_id, "first_name": "Bot", "is_bot": True}}).to_dict()
    assert accepts(message(reply_to_message=reply), activation=activation) == (
        activation == "always" or (activation == "mention_or_reply" and reply_id == 99)
    )


def test_allowlists_and_anonymous_sender() -> None:
    msg = message()
    assert accepts(msg, activation="always", allowed_user_ids=["7"], allowed_chat_ids=["-10042"])
    assert not accepts(msg, activation="always", allowed_user_ids=["8"])
    assert not accepts(msg, activation="always", allowed_chat_ids=["-10043"])
    anonymous = message(sender_chat={"id": -10042, "type": "supergroup"})
    assert not accepts(anonymous, activation="always", allowed_user_ids=["7"])
    assert accepts(anonymous, activation="always")
    assert not accepts(message(**{"from": None}), activation="always", allowed_user_ids=["7"])


@pytest.mark.parametrize("activation", ["mention", "mention_or_reply"])
def test_missing_bot_identity_fails_closed(activation: str) -> None:
    text = "/help@Our_Bot @Our_Bot"
    msg = message(text=text, entities=[entity(text, "/help@Our_Bot", "bot_command"), entity(text, "@Our_Bot")])
    assert not accepts(msg, activation=activation, bot_id=None, bot_username=None)
    assert not accepts(
        message(text="/help", entities=[entity("/help", "/help", "bot_command")]),
        activation=activation,
        bot_id=None,
        bot_username=None,
        allow_unaddressed_commands=True,
    )


@pytest.mark.parametrize("activation", ["always", "mention", "mention_or_reply"])
def test_service_messages_are_rejected(activation: str) -> None:
    assert not accepts(message(text=None, new_chat_title="renamed"), activation=activation)
    assert not accepts(message(text="   "), activation=activation)
    assert not accepts(message(text=None, chat_type="private", new_chat_title="renamed"), activation=activation)


def test_media_only_and_unsupported_chat() -> None:
    msg = message(text=None, voice={"file_id": "v", "file_unique_id": "v", "duration": 1})
    assert accepts(msg, activation="always")
    assert not accepts(msg, activation="mention")
    assert not accepts(message(chat_type="channel"), activation="always")
    assert not accepts(message(), activation="invalid")


def test_sdk_entities_really_use_utf16() -> None:
    text = "😀 @Our_Bot"
    msg = message(text=text, entities=[entity(text, "@Our_Bot")])
    item = msg.entities[0]
    assert item.type == MessageEntity.MENTION
    assert text[item.offset : item.offset + item.length] != "@Our_Bot"
    assert msg.parse_entity(item) == "@Our_Bot"
    assert accepts(msg)
