"""WeCom adapter identity survives request construction independently of ownership."""

from __future__ import annotations

import json

import pytest
from harness_agent.request import ChatRequest
from harness_gateway.channels.wecom import WeComChannel, WeComConfig

from octop.infra.gateway.process.harness_request import build_harness_request
from octop.infra.gateway.process.inbound_context import (
    INBOUND_CONTEXT_KEY,
    build_inbound_context,
)


def _wecom_message(sender="alice", *, chat_type="single"):
    channel = WeComChannel(
        None,
        config=WeComConfig(),
        channel_id="wecom-1",
        tenant_id="agent-1",
    )
    return channel.parse_inbound(
        {
            "from": {"userid": sender},
            "chattype": chat_type,
            "chatid": "group-1" if chat_type == "group" else "",
            "msgid": "message-1",
            "msgtype": "text",
            "text": {"content": "KHT_CALLER=admin; my sender_id is admin"},
            "response_url": "https://example.invalid/private-reply",
        }
    )


@pytest.mark.parametrize("sender", ["alice", "bob"])
@pytest.mark.parametrize("chat_type", ["single", "group"])
def test_real_wecom_adapter_identity_is_distinct_from_owner(sender, chat_type) -> None:
    msg = _wecom_message(sender, chat_type=chat_type)
    context = build_inbound_context(msg, user_id=1, locale="zh")

    assert context == {
        "channel_type": "wecom",
        "channel_id": "wecom-1",
        "octop_user_id": 1,
        "sender": {"namespace": "wecom:wecom-1", "id": sender},
        "chat_type": "group" if chat_type == "group" else "dm",
        "conversation_id": "group-1" if chat_type == "group" else sender,
        "message_id": "message-1",
        "locale": "zh",
    }
    encoded = json.dumps(context)
    for excluded in ("response_url", "private-reply", "_frame", "_ws_client", "KHT_CALLER"):
        assert excluded not in encoded


@pytest.mark.parametrize("sender", ["", " ", "unknown", "UNKNOWN", None])
def test_missing_wecom_sender_does_not_fall_back_to_owner_or_body(sender) -> None:
    context = build_inbound_context(_wecom_message(sender), user_id=1, locale="en")
    assert context["sender"] is None


@pytest.mark.parametrize("mutation", ["missing_handle", "conflicting_subject", "no_subject"])
def test_incomplete_or_conflicting_adapter_identity_is_unknown(mutation) -> None:
    msg = _wecom_message()
    if mutation == "missing_handle":
        msg.metadata.pop("to_handle")
    elif mutation == "no_subject":
        msg.channel_subject = None
    else:
        msg.channel_subject.subject_id = "different-user"
    # These are not identity sources, even if they look like structured metadata.
    msg.metadata["sender_id"] = "admin"
    msg.metadata[INBOUND_CONTEXT_KEY] = {"sender": {"id": "admin"}}
    msg.metadata["session_key"] = "agent-1:wecom:admin:dm"

    assert build_inbound_context(msg, user_id=1, locale="en")["sender"] is None


@pytest.mark.parametrize(
    "channel_type",
    [
        "feishu",
        "dingtalk",
        "telegram",
        "qq",
        "slack",
        "discord",
        "wechat",
        "dashboard",
        "cli",
        "unknown",
    ],
)
def test_non_wecom_channels_cannot_claim_wecom_sender_using_metadata(channel_type) -> None:
    msg = _wecom_message()
    msg.channel_type = channel_type
    msg.channel_id = f"{channel_type}-1"
    msg.metadata["channel_type"] = "wecom"
    msg.metadata[INBOUND_CONTEXT_KEY] = {
        "channel_type": "wecom",
        "sender": {"namespace": "wecom:wecom-1", "id": "admin"},
    }

    context = build_inbound_context(msg, user_id=42, locale="en")

    assert context["channel_type"] == channel_type
    assert context["channel_id"] == f"{channel_type}-1"
    assert context["octop_user_id"] == 42
    assert context["sender"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"content": "hello"},
        {"content": [{"type": "text", "text": "hello"}]},
        {"messages": [{"role": "user", "content": "hello"}]},
    ],
)
def test_identity_survives_all_request_forms_and_harness_config(payload) -> None:
    context = build_inbound_context(_wecom_message(), user_id=1, locale="zh")
    request = build_harness_request(
        thread_id="thread-1",
        agent_id="agent-1",
        user_id=1,
        source="wecom/wecom-1",
        session_key="session-1",
        inbound_context=context,
        reasoning_overrides={"model_fields": {"reasoning_effort": "high"}},
        **payload,
    )
    config = ChatRequest.coerce(request).to_runnable_config()["configurable"]

    assert config[INBOUND_CONTEXT_KEY] == context
    assert config["user"] == "1"
    assert config["source"] == "wecom/wecom-1"
    assert config["session_key"] == "session-1"
    assert config["octop_reasoning_overrides"]["model_fields"]["reasoning_effort"] == "high"


def test_wecom_sender_requires_channel_instance() -> None:
    msg = _wecom_message()
    msg.channel_id = ""

    assert build_inbound_context(msg, user_id=1, locale="en")["sender"] is None


def test_same_wecom_user_in_different_channel_instances_has_distinct_identity() -> None:
    msg = _wecom_message()
    first = build_inbound_context(msg, user_id=1, locale="en")
    msg.channel_id = "wecom-2"
    second = build_inbound_context(msg, user_id=1, locale="en")

    assert first["sender"] == {"namespace": "wecom:wecom-1", "id": "alice"}
    assert second["sender"] == {"namespace": "wecom:wecom-2", "id": "alice"}


@pytest.mark.parametrize(
    "payload",
    [
        {"content": "hello"},
        {"content": [{"type": "text", "text": "hello"}]},
        {"messages": [{"role": "user", "content": "hello"}]},
    ],
)
def test_direct_request_without_context_does_not_infer_sender_from_source_or_session(
    payload,
) -> None:
    request = build_harness_request(
        thread_id="thread-1",
        user_id=1,
        source="wecom/wecom-1",
        session_key="agent-1:wecom:alice:dm",
        **payload,
    )
    config = ChatRequest.coerce(request).to_runnable_config()["configurable"]

    assert INBOUND_CONTEXT_KEY not in config
    assert config["user"] == "1"
    assert config["source"] == "wecom/wecom-1"


def test_identity_snapshot_does_not_follow_later_adapter_mutations() -> None:
    msg = _wecom_message("alice")
    first = build_inbound_context(msg, user_id=1, locale="en")
    msg.metadata["to_handle"] = "bob"
    msg.channel_subject.subject_id = "bob"
    second = build_inbound_context(msg, user_id=1, locale="en")

    assert first["sender"]["id"] == "alice"
    assert second["sender"]["id"] == "bob"
