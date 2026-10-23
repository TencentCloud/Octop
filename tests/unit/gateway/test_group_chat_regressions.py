"""Host-owned group choice liveness, quote prompts and rejection notices."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from octop_gateway.models import TextContent
from tests.unit.gateway.test_telegram_bridge import setup_bridge

from octop.infra.gateway.channels.telegram_bridge import TelegramBridge, _ButtonReply, _ButtonState


def _bridge(thread_binding):
    hitl = SimpleNamespace(
        store=SimpleNamespace(
            get_pending=lambda pid, **kw: SimpleNamespace(
                ask_question_index=0, user_id=1, session_key="s", thread_id="new-thread"
            )
        )
    )
    gw = SimpleNamespace(
        processor=SimpleNamespace(hitl_coordinator=hitl),
        thread_registry=SimpleNamespace(get_bound_thread_id=lambda _: thread_binding),
        _repos=SimpleNamespace(
            agent_repo=SimpleNamespace(get=lambda _: SimpleNamespace(user_id=1))
        ),
    )
    return TelegramBridge(gw, lambda m: None, "tg")


def _reply(state):
    from octop_gateway.models import ChannelSubject, InboundMessage, TextContent

    subject = ChannelSubject(subject_id="-100", chat_type="group", metadata={"chat_id": "-100"})
    base = InboundMessage(
        channel_id="tg",
        channel_type="telegram",
        tenant_id="sites",
        channel_subject=subject,
        content=[TextContent(text="1")],
        metadata={"chat_id": "-100", "user_id": "7", "is_group": True},
    )
    return _ButtonReply(**base.model_dump(), button_state=state)


@pytest.mark.parametrize("binding", ["old-thread", "new-thread"])
def test_choice_button_survives_group_thread_rebind(binding):
    """群里每轮都会重绑 thread；只要 pending 记录仍属于该会话/用户，按钮就该生效。"""
    bridge = _bridge(binding)
    state = _ButtonState(
        owner_id=1,
        thread_id="old-thread",
        pending_id="p1",
        question_index=0,
        model_page=None,
        text="1",
    )
    assert bridge._button_reject_reason(_reply(state), state, "sites", "s") is None


def test_stale_choice_button_is_still_rejected():
    bridge = _bridge("new-thread")
    state = _ButtonState(
        owner_id=1,
        thread_id="old-thread",
        pending_id="p1",
        question_index=5,
        model_page=None,
        text="1",
    )
    assert (
        bridge._button_reject_reason(_reply(state), state, "sites", "s") == "question_index_changed"
    )


@pytest.mark.asyncio
async def test_rejected_button_sends_notice_without_typing():
    """按钮失效必须给用户提示，而不是静默丢弃；不先发 typing 白占限流额度。"""
    bridge, msg, channel, record = setup_bridge()
    sent = []
    typing = []

    async def fake_send(subject, text):
        sent.append(text)

    async def fake_typing(subject):
        typing.append(subject)

    channel.push_text = fake_send
    channel._send_typing_indicator = fake_typing
    channel.enqueue = MagicMock()
    bridge.gateway.thread_registry.get_bound_thread_id = lambda _: "someone-else"
    # 组装一条按钮回复
    reply = msg.model_copy(
        update={"content": [TextContent(text="1")], "metadata": {"user_id": "telegram-user"}}
    )
    from octop.infra.gateway.channels.telegram_bridge import _ButtonReply, _ButtonState

    state = _ButtonState(
        owner_id=0, thread_id="t1", pending_id="p1", question_index=0, model_page=None, text="1"
    )
    button_reply = _ButtonReply(**reply.model_dump(), button_state=state)
    _ = [event async for event in bridge(button_reply)]
    assert typing == [], "提示前不发 typing"
    assert sent == ["This card does not belong to the current session."]
    channel.enqueue.assert_not_called()


def _nav_state():
    return _ButtonState(
        owner_id=1, thread_id="old-thread", pending_id=None, question_index=0, model_page=1, text=""
    )


def test_model_menu_buttons_survive_thread_rebind_in_groups():
    """群聊里别人的新消息会重绑 thread，翻页等导航按钮不能因此失效。"""
    bridge = _bridge("new-thread")
    reply = _reply(_nav_state())
    assert bridge._button_reject_reason(reply, reply.button_state, "sites", "s") is None


def test_model_menu_buttons_stay_strict_in_private_chats():
    bridge = _bridge("new-thread")
    reply = _reply(_nav_state())
    reply = reply.model_copy(update={"metadata": {**reply.metadata, "is_group": False}})
    assert bridge._button_reject_reason(reply, reply.button_state, "sites", "s") == "thread_rebound"


@pytest.mark.asyncio
async def test_reject_notice_follows_user_locale():
    bridge, msg, channel, record = setup_bridge()
    bridge.gateway._repos.user_repo = SimpleNamespace(get=lambda _id: SimpleNamespace(locale="zh"))
    sent = []

    async def fake_send(subject, text):
        sent.append(text)

    channel.push_text = fake_send
    state = _ButtonState(
        owner_id=0, thread_id="t1", pending_id="p1", question_index=0, model_page=None, text="1"
    )
    reply = msg.model_copy(update={"content": [TextContent(text="1")]})
    _ = [e async for e in bridge(_ButtonReply(**reply.model_dump(), button_state=state))]
    assert sent == ["该卡片不属于当前会话"]


@pytest.mark.asyncio
async def test_choice_card_falls_back_to_text_when_buttons_fail():
    """send_buttons 抛错时被扣住的文本卡片必须补发，不能丢。"""
    bridge, msg, channel, record = setup_bridge()
    channel.send_buttons.side_effect = RuntimeError("telegram down")
    events = [event async for event in bridge(msg)]
    assert [e.type.value for e in events].count("message") == 1
    assert events[-1].type.value == "completed"


@pytest.mark.asyncio
async def test_buttons_are_registered_with_hitl_aligned_ttl():
    bridge, msg, channel, record = setup_bridge()
    _ = [event async for event in bridge(msg)]
    assert channel.send_buttons.call_args.kwargs["ttl"] == 1800.0
