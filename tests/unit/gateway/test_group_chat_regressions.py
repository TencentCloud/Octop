"""Group-chat regressions: choice-button liveness, quotes, mentions, topic scope."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from octop_gateway.models import MessageEvent, TextContent
from tests.unit.gateway.test_telegram_bridge import setup_bridge

import octop.infra.gateway.channels.telegram_interaction as tinter
import octop.infra.gateway.channels.telegram_reply_quote as tquote
from octop.infra.gateway.channels.telegram_bridge import TelegramBridge, _ButtonReply, _ButtonState


# --- choice button liveness in groups -------------------------------------
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


# --- fix-plan regressions: reply quote / reject notice / interaction ttl ---
@pytest.mark.asyncio
async def test_reply_quote_is_injected_into_prompt():
    """引用消息正文必须进 prompt，而 gateway 只传 id。"""
    bridge, msg, channel, record = setup_bridge()
    quoted = "Please review the deploy checklist"
    msg = msg.model_copy(
        update={
            "content": [TextContent(text="looks fine")],
            "metadata": {
                **msg.metadata,
                "reply_quote_text": quoted,
            },
        }
    )
    seen = []

    async def processor(message):
        seen.append(message.text)
        yield MessageEvent.completed()

    bridge.processor = processor
    _ = [event async for event in bridge(msg)]
    assert quoted in seen[0]
    assert "[Quoted message]" in seen[0]
    assert "[Current message]" in seen[0]
    assert "looks fine" in seen[0]


@pytest.mark.asyncio
async def test_plain_message_unchanged_and_mention_stripped():
    bridge, msg, channel, record = setup_bridge()
    channel._bot_username = "webmaster_bot"
    msg = msg.model_copy(update={"content": [TextContent(text="@webmaster_bot, deploy status?")]})
    seen = []

    async def processor(message):
        seen.append(message.text)
        yield MessageEvent.completed()

    bridge.processor = processor
    _ = [event async for event in bridge(msg)]
    assert seen[0] == "deploy status?", "前缀 @mention 必须被剥掉"


@pytest.mark.asyncio
async def test_mid_text_mention_is_not_stripped():
    bridge, msg, channel, record = setup_bridge()
    msg = msg.model_copy(update={"content": [TextContent(text="please ping @hr about this")]})
    seen = []

    async def processor(message):
        seen.append(message.text)
        yield MessageEvent.completed()

    bridge.processor = processor
    _ = [event async for event in bridge(msg)]
    assert seen[0] == "please ping @hr about this"


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

    channel._send_text = fake_send
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
async def test_reject_notice_and_quote_follow_user_locale():
    bridge, msg, channel, record = setup_bridge()
    bridge.gateway._repos.user_repo = SimpleNamespace(get=lambda _id: SimpleNamespace(locale="zh"))
    sent = []

    async def fake_send(subject, text):
        sent.append(text)

    channel._send_text = fake_send
    state = _ButtonState(
        owner_id=0, thread_id="t1", pending_id="p1", question_index=0, model_page=None, text="1"
    )
    reply = msg.model_copy(update={"content": [TextContent(text="1")]})
    _ = [e async for e in bridge(_ButtonReply(**reply.model_dump(), button_state=state))]
    assert sent == ["该卡片不属于当前会话"]

    seen = []

    async def processor(message):
        seen.append(message.text)
        yield MessageEvent.completed()

    bridge.processor = processor
    quoted = msg.model_copy(update={"metadata": {**msg.metadata, "reply_to_text": "旧消息"}})
    _ = [e async for e in bridge(quoted)]
    assert seen[0].startswith("[引用消息]\n旧消息\n\n[当前消息]\n")


@pytest.mark.asyncio
async def test_interaction_topic_none_relaxed_but_user_and_chat_strict():
    tinter.install()
    from octop_gateway.channels.telegram.interaction import Interactions

    ran = []

    async def action():
        ran.append(1)

    inter = Interactions()
    token = inter.register("u", "c", None, action)
    assert await inter.invoke(token, "other", "c", 5) is False
    assert await inter.invoke(token, "u", "other-chat", 5) is False
    assert ran == []
    assert await inter.invoke(token, "u", "c", 5) is True
    assert ran == [1]
    # 已消费
    assert await inter.invoke(token, "u", "c", 5) is False


@pytest.mark.asyncio
async def test_interaction_topic_set_stays_strict():
    tinter.install()
    from octop_gateway.channels.telegram.interaction import Interactions

    inter = Interactions()
    token = inter.register("u", "c", 7, AsyncMock())
    assert await inter.invoke(token, "u", "c", 8) is False
    assert await inter.invoke(token, "u", "c", 7) is True


class _FakeChannel:
    _bot_id = 100

    async def _extract_message(self, message, *, edited=False):
        return {"chat_id": "1"}


def _msg(reply_text=None, reply_from=7, quote=None):
    reply = (
        SimpleNamespace(text=reply_text, caption=None, from_user=SimpleNamespace(id=reply_from))
        if reply_text is not None
        else None
    )
    return SimpleNamespace(
        reply_to_message=reply, quote=SimpleNamespace(text=quote) if quote else None
    )


@pytest.mark.asyncio
async def test_reply_quote_extractor_adds_fields():
    tquote._wrap_extract(_FakeChannel)
    data = await _FakeChannel()._extract_message(_msg("quoted body", quote="inline"))
    assert data["reply_to_text"] == "quoted body"
    assert data["reply_quote_text"] == "inline"


@pytest.mark.asyncio
async def test_reply_quote_skips_bots_own_message_and_caps_length():
    tquote._wrap_extract(_FakeChannel)
    own = await _FakeChannel()._extract_message(_msg("my earlier answer", reply_from=100))
    assert own["reply_to_text"] is None
    long = await _FakeChannel()._extract_message(_msg("x" * 5000))
    assert len(long["reply_to_text"]) == 2000


# --- async _extract_message must be awaited (regression: coroutine never awaited) ---
@pytest.mark.asyncio
async def test_reply_quote_extractor_must_be_async():
    tquote.install()
    from octop_gateway.channels.telegram.channel import TelegramChannel

    assert getattr(TelegramChannel._extract_message, "__octop_telegram_reply_quote__", False)

    class FakeReply:
        message_id = 11
        text = "quoted body"
        caption = None

    class FakeQuote:
        text = "inline quote"

    class FakeMessage:
        reply_to_message = FakeReply()
        quote = FakeQuote()

    captured = {}

    async def fake_base(self, message, *args, **kwargs):
        captured["called"] = True
        return {"chat_id": "1"}

    import octop.infra.gateway.channels.telegram_reply_quote as mod

    mod.install()
    ch = object()
    # 直接调用包装层函数，验证其为协程并正确 await
    from types import MethodType

    MethodType(TelegramChannel._extract_message, ch)
    # 替换 base 闭包无法直接访问，用另一条路：验证函数是 async
    import inspect

    assert inspect.iscoroutinefunction(TelegramChannel._extract_message), (
        "_extract_message 必须是 async def"
    )


# --- reply quote passes through parse_inbound whitelist ---


@pytest.mark.asyncio
async def test_reply_quote_survives_parse_inbound_whitelist():
    """parse_inbound 的硬编码白名单会丢掉引用正文，必须透传。"""
    tquote.install()
    from octop_gateway.channels.telegram.channel import TelegramChannel

    ch = TelegramChannel.__new__(TelegramChannel)
    ch._channel_id = "tg"
    ch._channel_type = "telegram"
    ch._tenant_id = None
    ch._config = SimpleNamespace(topic_isolation=False)
    ch._connection_session = "sess"

    payload = {
        "chat_id": "-100",
        "user_id": "7",
        "message_id": "42",
        "content": [{"type": "text", "text": "what about this?"}],
        "is_group": True,
        "reply_to_message_id": 41,
        "reply_to_text": "deploy checklist",
        "reply_quote_text": "checklist",
    }
    message = ch.parse_inbound(payload)
    assert message.metadata.get("reply_to_text") == "deploy checklist"
    assert message.metadata.get("reply_quote_text") == "checklist"
    assert message.metadata.get("reply_to_message_id") == 41
    assert "content" not in message.metadata, "载荷里的 content 不能漏进 metadata"


@pytest.mark.asyncio
async def test_message_text_untouched_when_bot_username_unknown():
    """用户名未知（通道未就绪）时不剥离任何 @，也不动缩进。"""
    bridge, msg, channel, record = setup_bridge()
    raw = "@somebot run\n    indented  code"
    msg = msg.model_copy(update={"content": [TextContent(text=raw)]})
    seen = []

    async def processor(message):
        seen.append(message.text)
        yield MessageEvent.completed()

    bridge.processor = processor
    _ = [event async for event in bridge(msg)]
    assert seen[0] == raw


@pytest.mark.asyncio
async def test_mention_strip_keeps_code_indentation():
    """剥离提及不能顺带抹掉正文里的缩进和多空格。"""
    bridge, msg, channel, record = setup_bridge()
    channel._bot_username = "denAIAssistantBot"
    raw = "@denAIAssistantBot fix:\ndef f():\n    return  1"
    msg = msg.model_copy(update={"content": [TextContent(text=raw)]})
    seen = []

    async def processor(message):
        seen.append(message.text)
        yield MessageEvent.completed()

    bridge.processor = processor
    _ = [event async for event in bridge(msg)]
    assert seen[0] == "fix:\ndef f():\n    return  1"


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


# --- bot mention exclusion (Telegram usernames must end with "bot") ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("@denAIAssistantBot, hello", "hello"),
        ("@denAIAssistantBot check the site", "check the site"),
        ("does @denaiassistantbot know?", "does know?"),
        ("line one\n@denAIAssistantBot line two", "line one\nline two"),
        # 其他 @ 可能是正文语义：其他 bot、普通用户、邮箱、名字里含 bot 的词
        ("ask @home_butler_bot and @hr together", "ask @home_butler_bot and @hr together"),
        ("ping @hr about it", "ping @hr about it"),
        ("mail john@abbot.com", "mail john@abbot.com"),
        ("@robot please", "@robot please"),
        ("@denAIAssistantBotX stays", "@denAIAssistantBotX stays"),
    ],
)
async def test_own_bot_mention_never_reaches_the_prompt(raw, expected):
    """只剥离本 bot 的用户名；别的 @ 保留。"""
    bridge, msg, channel, record = setup_bridge()
    channel._bot_username = "denAIAssistantBot"
    msg = msg.model_copy(update={"content": [TextContent(text=raw)]})
    seen = []

    async def processor(message):
        seen.append(message.text)
        yield MessageEvent.completed()

    bridge.processor = processor
    _ = [event async for event in bridge(msg)]
    assert seen[0] == expected


@pytest.mark.asyncio
async def test_mid_text_non_bot_mention_is_preserved():
    """非 bot 的中段提及保留：可能是正文语义（例如 @hr）。"""
    bridge, msg, channel, record = setup_bridge()
    msg = msg.model_copy(update={"content": [TextContent(text="ask @hr to review")]})
    seen = []

    async def processor(message):
        seen.append(message.text)
        yield MessageEvent.completed()

    bridge.processor = processor
    _ = [event async for event in bridge(msg)]
    assert seen[0] == "ask @hr to review"


@pytest.mark.asyncio
async def test_non_topic_thread_id_is_logged(caplog):
    tquote._wrap_extract(_FakeChannel)
    plain = SimpleNamespace(
        message_thread_id=41,
        is_topic_message=False,
        chat=SimpleNamespace(type="supergroup", id=-100),
        message_id=42,
        reply_to_message=None,
        quote=None,
    )
    forum = SimpleNamespace(**{**vars(plain), "is_topic_message": True})
    with caplog.at_level("INFO"):
        await _FakeChannel()._extract_message(forum)
        assert "carries thread id" not in caplog.text
        await _FakeChannel()._extract_message(plain)
    assert "chat=-100 thread=41 message=42" in caplog.text


@pytest.mark.asyncio
async def test_callback_topic_difference_is_logged(caplog):
    tinter.install()
    from octop_gateway.channels.telegram.interaction import Interactions

    inter = Interactions()
    token = inter.register("u", "c", None, AsyncMock())
    with caplog.at_level("INFO"):
        assert await inter.invoke(token, "u", "c", 41) is True
    assert "registered=None actual=41" in caplog.text
