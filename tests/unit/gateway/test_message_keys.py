"""Unit tests for IM session/user key derivation."""

from __future__ import annotations

from octop_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.gateway.process.message_keys import (
    resolve_user_id_for_message,
    sanitize_im_metadata,
    session_key_from_message,
    user_id_from_message,
)


def _msg(*, subject_id: str, channel_type: str = "qq") -> InboundMessage:
    return InboundMessage(
        channel_type=channel_type,
        channel_id="ch1",
        channel_subject=ChannelSubject(subject_id=subject_id),
        content=[TextContent(text="hi")],
        text="hi",
    )


def test_user_id_from_numeric_dashboard_subject() -> None:
    msg = _msg(subject_id="42", channel_type="dashboard")
    assert user_id_from_message(msg) == 42


def test_resolve_user_id_uses_owner_for_numeric_external_subject() -> None:
    msg = _msg(subject_id="42", channel_type="dingtalk")
    assert resolve_user_id_for_message(msg, agent_owner_id=7) == 7


def test_resolve_user_id_falls_back_to_agent_owner_for_openid() -> None:
    msg = _msg(subject_id="openid_abc123")
    assert resolve_user_id_for_message(msg, agent_owner_id=7) == 7


def test_resolve_user_id_zero_without_owner() -> None:
    msg = _msg(subject_id="openid_abc123")
    assert resolve_user_id_for_message(msg, agent_owner_id=None) == 0


def test_group_session_is_owned_by_conversation_not_sender() -> None:
    msg = InboundMessage(
        channel_type="qq",
        channel_id="ch1",
        channel_subject=ChannelSubject(subject_id="group-openid", chat_type="group"),
        content=[TextContent(text="hi")],
        metadata={
            "chat_type": "group",
            "conversation_id": "group-openid",
            "sender_id": "member-openid",
        },
    )

    key = session_key_from_message(msg, agent_id="agent-1")

    assert "group-openid" in key
    assert "member-openid" not in key


def test_sanitize_im_metadata_persists_xiaoyi_routing() -> None:
    msg = InboundMessage(
        channel_type="xiaoyi",
        channel_id="ch-xy",
        channel_subject=ChannelSubject(subject_id="sess-1"),
        content=[TextContent(text="hi")],
        metadata={
            "session_id": "sess-1",
            "task_id": "task-9",
            "msg_id": "ephemeral",
        },
    )
    meta = sanitize_im_metadata(msg)
    assert meta["session_id"] == "sess-1"
    assert meta["task_id"] == "task-9"
    assert "msg_id" not in meta


def test_sanitize_im_metadata_persists_weixin_routing() -> None:
    msg = InboundMessage(
        channel_type="weixin",
        channel_id="ch-wx",
        channel_subject=ChannelSubject(subject_id="user@im.wechat"),
        content=[TextContent(text="hi")],
        metadata={
            "account_id": "bot-1",
            "from_user_id": "user@im.wechat",
            "context_token": "ctx-abc",
            "message_id": "mid-1",
        },
    )
    meta = sanitize_im_metadata(msg)
    assert meta["account_id"] == "bot-1"
    assert meta["from_user_id"] == "user@im.wechat"
    assert "context_token" not in meta
    assert "message_id" not in meta


def _telegram_message(**metadata: object) -> InboundMessage:
    msg = _msg(subject_id="-100123", channel_type="telegram")
    msg.metadata = {"chat_type": "group", "chat_id": -100123, **metadata}
    return msg


def test_telegram_topic_isolation_is_opt_in() -> None:
    legacy = session_key_from_message(_telegram_message(), agent_id="a1")
    assert legacy == "a1:telegram:-100123:group"
    for flag in (None, False, "true"):
        msg = _telegram_message(topic_isolation=flag, message_thread_id=42)
        assert session_key_from_message(msg, agent_id="a1") == legacy


def test_telegram_isolation_separates_chat_topic_instance_and_agent() -> None:
    msg = _telegram_message(topic_isolation=True, message_thread_id=42)
    first = session_key_from_message(msg, agent_id="a1")
    msg.metadata["message_thread_id"] = 43
    second = session_key_from_message(msg, agent_id="a1")
    msg.channel_id = "ch2"
    third = session_key_from_message(msg, agent_id="a1")
    msg.metadata["chat_id"] = -100456
    fourth = session_key_from_message(msg, agent_id="a1")
    fifth = session_key_from_message(msg, agent_id="a2")
    assert len({first, second, third, fourth, fifth}) == 5
    assert first == "a1:telegram:ch1/-100123/42:group"


def test_telegram_missing_topic_uses_main_chat_and_preserves_explicit_key() -> None:
    msg = _telegram_message(topic_isolation=True)
    assert session_key_from_message(msg, agent_id="a1") == "a1:telegram:ch1/-100123/0:group"
    msg.metadata["session_key"] = " existing-session "
    assert session_key_from_message(msg, agent_id="a1") == "existing-session"


def test_topic_isolation_metadata_does_not_change_other_channels() -> None:
    msg = _telegram_message(topic_isolation=True, message_thread_id=42)
    msg.channel_type = "qq"
    assert session_key_from_message(msg, agent_id="a1") == "a1:qq:-100123:group"


def test_telegram_durable_topic_metadata_excludes_source_reply_ids() -> None:
    msg = _telegram_message(
        topic_isolation=True,
        message_thread_id=42,
        message_id=123,
        source_message_id=123,
        reply_to_message_id=122,
    )
    assert sanitize_im_metadata(msg) == {
        "channel_type": "telegram",
        "chat_type": "group",
        "chat_id": -100123,
        "topic_isolation": True,
        "message_thread_id": 42,
    }
