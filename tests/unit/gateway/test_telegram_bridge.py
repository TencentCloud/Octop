"""Host bridge tests run with both released and new Gateway transports."""

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from octop_gateway.models import (
    ChannelSubject,
    InboundMessage,
    MessageEvent,
    MessageEventType,
    TextContent,
)

from octop.infra.errors import OctopError
from octop.infra.gateway.channels.telegram_bridge import TelegramBridge, validate_telegram_config
from octop.infra.gateway.hitl.coordinator import HitlChannelCoordinator, HitlStreamContext
from octop.infra.gateway.process.message_keys import session_key_from_message


def setup_bridge():
    msg = InboundMessage(
        channel_id="tg",
        channel_type="telegram",
        tenant_id="agent",
        channel_subject=ChannelSubject(subject_id="chat"),
        content=[TextContent(text="hello")],
        metadata={"user_id": "telegram-user", "chat_id": "chat", "message_thread_id": 7},
    )
    hitl = HitlChannelCoordinator()
    record = hitl.register_from_request(
        {
            "action_requests": [
                {
                    "name": "ask_user_question",
                    "args": {
                        "questions": [
                            {
                                "question": "Pick",
                                "options": [{"label": "Alpha"}, {"label": "Beta"}],
                            },
                            {"question": "Next", "options": [{"label": "Gamma"}]},
                        ]
                    },
                }
            ]
        },
        ctx=HitlStreamContext(
            thread_id="thread",
            agent_id="agent",
            user_id=1,
            session_key=session_key_from_message(msg, agent_id="agent"),
            channel_type="telegram",
        ),
    )
    channel = SimpleNamespace(
        send_buttons=AsyncMock(),
        _process_inbound=AsyncMock(),
        enqueue=MagicMock(),
        get_debounce_key=lambda msg: "chat",
    )

    async def run_in_session(channel_id, key, operation):
        assert (channel_id, key) == ("tg", "chat")
        return await operation()

    gateway = SimpleNamespace(
        channel_manager=SimpleNamespace(
            get_channel=lambda _: channel, run_in_session=run_in_session
        ),
        processor=SimpleNamespace(hitl_coordinator=hitl),
        thread_registry=SimpleNamespace(get_bound_thread_id=lambda _: "thread"),
        _repos=SimpleNamespace(
            agent_repo=SimpleNamespace(get=lambda _: SimpleNamespace(user_id=1))
        ),
        _agent_manager=SimpleNamespace(cancel_stream=MagicMock()),
    )

    async def processor(msg):
        yield MessageEvent.text("question", metadata={"octop_hitl_pending_id": record.pending_id})
        yield MessageEvent.completed()

    return TelegramBridge(gateway, processor, "tg"), msg, channel, record


async def drain_button(bridge, channel):
    reply = channel.enqueue.call_args.args[0]
    processor = bridge.processor

    async def deliver(msg):
        await channel._process_inbound(msg, msg.channel_subject)
        if False:
            yield

    bridge.processor = deliver
    try:
        _ = [event async for event in bridge(reply)]
    finally:
        bridge.processor = processor


@pytest.mark.asyncio
async def test_callback_returns_before_session_lock_and_agent_turn():
    bridge, msg, channel, record = setup_bridge()
    channel.enqueue = MagicMock()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def busy_session(channel_id, key, operation):
        entered.set()
        await release.wait()
        await operation()

    bridge.gateway.channel_manager.run_in_session = busy_session
    action = bridge._action(msg, msg.channel_subject, "1", record.pending_id)
    task = asyncio.create_task(action())
    try:
        await asyncio.sleep(0)
        assert task.done(), "Telegram callback is waiting for session execution"
        await task
        channel.enqueue.assert_called_once()
        channel._process_inbound.assert_not_awaited()
    finally:
        release.set()
        await task


@pytest.mark.asyncio
async def test_choice_uses_original_scope_and_rejects_stale_siblings():
    bridge, msg, channel, record = setup_bridge()
    # 卡片文本被按钮取代：只发按钮 + 终止事件，不再重复发一条选项文本。
    events = [event async for event in bridge(msg)]
    assert [event.type for event in events] == [MessageEventType.COMPLETED]
    subject, text, actions = channel.send_buttons.call_args.args
    assert subject.metadata["user_id"] == "telegram-user"
    assert subject.metadata["message_thread_id"] == 7
    assert [label for label, _ in actions] == ["Alpha", "Beta"]
    await actions[0][1]()
    await drain_button(bridge, channel)
    reply = channel._process_inbound.call_args.args[0]
    assert reply.text == "1"
    assert reply.tenant_id == "agent"
    record.ask_question_index = 1
    await actions[1][1]()
    await drain_button(bridge, channel)
    channel._process_inbound.assert_awaited_once()


@pytest.mark.asyncio
async def test_choice_advances_existing_question_collector():
    bridge, msg, channel, record = setup_bridge()
    hitl = bridge.gateway.processor.hitl_coordinator

    async def process_reply(reply, subject):
        message, next_card = hitl.collect_ask_reply(record, reply.text, locale="en")
        assert message is None
        assert "Next" in next_card

    channel._process_inbound.side_effect = process_reply
    _ = [event async for event in bridge(msg)]
    await channel.send_buttons.call_args.args[2][1][1]()
    await drain_button(bridge, channel)
    assert record.ask_question_index == 1
    assert record.ask_answers == ["Beta"]


@pytest.mark.asyncio
async def test_multiselect_and_security_pause_do_not_offer_choices():
    bridge, msg, channel, record = setup_bridge()
    record.action_requests[0]["args"]["questions"][0]["multi_select"] = True
    _ = [event async for event in bridge(msg)]
    channel.send_buttons.assert_not_awaited()
    record.action_requests = [{"name": "execute", "args": {"command": "test"}}]
    _ = [event async for event in bridge(msg)]
    channel.send_buttons.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_or_rebound_pause_does_not_resume():
    bridge, msg, channel, record = setup_bridge()
    _ = [event async for event in bridge(msg)]
    action = channel.send_buttons.call_args.args[2][0][1]
    bridge.gateway.thread_registry.get_bound_thread_id = lambda _: "new-thread"
    await action()
    await drain_button(bridge, channel)
    channel._process_inbound.assert_not_awaited()
    bridge.gateway.thread_registry.get_bound_thread_id = lambda _: "thread"
    record.status = "expired"
    await action()
    await drain_button(bridge, channel)
    channel._process_inbound.assert_not_awaited()


@pytest.mark.asyncio
async def test_native_cancel_signals_task_runtime():
    import asyncio

    bridge, msg, channel, record = setup_bridge()

    async def cancelled(msg):
        raise asyncio.CancelledError
        yield  # pragma: no cover

    bridge.processor = cancelled
    with pytest.raises(asyncio.CancelledError):
        _ = [event async for event in bridge(msg)]
    bridge.gateway._agent_manager.cancel_stream.assert_called_once_with("agent", "thread")


@pytest.mark.asyncio
async def test_older_gateway_falls_back_to_text():
    bridge, msg, channel, record = setup_bridge()
    channel.send_buttons = None
    assert len([event async for event in bridge(msg)]) == 2
    channel._process_inbound.assert_not_awaited()


@pytest.mark.asyncio
async def test_invoke_mode_preserves_question_and_buttons_precede_completed():
    from octop_gateway.models import MessageEventType

    from octop.infra.gateway.process.response_mode import processor_for_response_mode

    bridge, msg, channel, record = setup_bridge()
    bridge.processor = processor_for_response_mode(bridge.processor, "invoke")
    async for event in bridge(msg):
        if event.type == MessageEventType.COMPLETED:
            channel.send_buttons.assert_awaited_once()
            break  # BaseChannel stops consuming here.


@pytest.mark.asyncio
async def test_model_choices_dispatch_existing_slash_path():
    bridge, msg, channel, record = setup_bridge()
    msg = msg.model_copy(
        update={
            "content": [TextContent(text="/model")],
            "metadata": {**msg.metadata, "reply_quote_text": "quoted source"},
        }
    )
    bridge.gateway.processor.hitl_coordinator.store.mark_resolved(record.pending_id, "expired")
    provider = SimpleNamespace(
        name="provider",
        enabled=1,
        api_key="key",
        get_models=lambda: [{"id": "model", "enabled": True}],
    )
    bridge.gateway._repos.provider_repo = SimpleNamespace(list_all=lambda: [provider])
    _ = [event async for event in bridge(msg)]
    actions = channel.send_buttons.call_args.args[2]
    assert actions[0][0] == "provider/model"
    await actions[0][1]()
    await drain_button(bridge, channel)
    assert channel._process_inbound.call_args.args[0].text == "/model provider/model"


@pytest.mark.asyncio
async def test_quoted_turn_does_not_change_native_answer_control_text():
    bridge, msg, channel, record = setup_bridge()
    msg = msg.model_copy(update={"metadata": {**msg.metadata, "reply_quote_text": "quoted source"}})
    _ = [event async for event in bridge(msg)]
    await channel.send_buttons.call_args.args[2][0][1]()
    await drain_button(bridge, channel)
    assert channel._process_inbound.call_args.args[0].text == "1"


@pytest.mark.asyncio
async def test_create_and_update_reject_before_persisting(monkeypatch):
    import octop_gateway.channels.telegram as telegram

    from octop.infra.gateway.gateway import ChannelCreateSpec, Gateway

    @dataclass
    class OldConfig:
        bot_token: str = ""

    monkeypatch.setattr(telegram, "TelegramConfig", OldConfig)
    repos = MagicMock()
    repos.channel_repo.get.return_value = SimpleNamespace(kind="telegram", config_json="{}")
    gateway = Gateway(agent_manager=MagicMock(), repos=repos)
    with pytest.raises(OctopError) as error:
        await gateway.create_channel(
            ChannelCreateSpec(
                channel_id="tg",
                agent_id="a",
                user_id=1,
                kind="telegram",
                name="tg",
                config={"streaming_mode": "edit"},
            )
        )
    assert "Gateway" in error.value.localized_message("en")
    repos.channel_repo.create.assert_not_called()
    with pytest.raises(OctopError):
        await gateway.update_channel("tg", config_json='{"topic_isolation": true}')
    repos.channel_repo.update.assert_not_called()


def test_old_gateway_options_fail_explicitly(monkeypatch):
    import octop_gateway.channels.telegram as telegram

    @dataclass
    class OldConfig:
        bot_token: str = ""

    monkeypatch.setattr(telegram, "TelegramConfig", OldConfig)
    validate_telegram_config("telegram", {"bot_token": "token"})
    with pytest.raises(OctopError, match="streaming_mode"):
        validate_telegram_config("telegram", {"bot_token": "token", "streaming_mode": "edit"})
    validate_telegram_config("other", {"streaming_mode": "edit"})


@pytest.mark.asyncio
async def test_model_pagination_and_revoked_model():
    bridge, msg, channel, record = setup_bridge()
    msg = msg.model_copy(update={"content": [TextContent(text="/models")]})
    models = [{"id": f"m{i:03}", "enabled": True} for i in range(105)]
    models.extend([{"id": "disabled", "enabled": False}, {"id": "embedding", "task": "embedding"}])
    provider = SimpleNamespace(name="p", enabled=1, api_key="key", get_models=lambda: models)
    bridge.gateway._repos.provider_repo = SimpleNamespace(list_all=lambda: [provider])
    bridge.gateway.processor.hitl_coordinator.store.mark_resolved(record.pending_id, "expired")
    seen = []

    async def processor(message):
        seen.append(message.text)
        yield MessageEvent.completed()

    bridge.processor = processor
    _ = [event async for event in bridge(msg)]
    assert seen == ["/models"]
    all_labels = set()
    for page in range(3):
        actions = channel.send_buttons.call_args.args[2]
        assert len(actions) <= 50
        all_labels.update(label for label, _ in actions if label.startswith("p/"))
        if page < 2:
            await next(action for label, action in actions if label == "→")()
            await drain_button(bridge, channel)
    assert all_labels == {f"p/m{i:03}" for i in range(105)}
    last_action = next(action for label, action in actions if label == "p/m104")
    models[104]["enabled"] = False
    await last_action()
    await drain_button(bridge, channel)
    channel._process_inbound.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_rejects_owner_change():
    bridge, msg, channel, record = setup_bridge()
    _ = [event async for event in bridge(msg)]
    action = channel.send_buttons.call_args.args[2][0][1]
    bridge.gateway._repos.agent_repo.get = lambda _: SimpleNamespace(user_id=2)
    await action()
    await drain_button(bridge, channel)
    channel._process_inbound.assert_not_awaited()


@pytest.mark.asyncio
async def test_unrelated_turn_does_not_reveal_pending_question():
    bridge, msg, channel, record = setup_bridge()

    async def processor(message):
        yield MessageEvent.completed()

    bridge.processor = processor
    _ = [event async for event in bridge(msg)]
    channel.send_buttons.assert_not_awaited()


def test_legacy_enabled_is_host_owned():
    validate_telegram_config("telegram", {"bot_token": "token", "enabled": "true"})


def test_invalid_gateway_option_values_rejected():
    with pytest.raises(OctopError):
        validate_telegram_config("telegram", {"group_activation": "unsupported"})


@pytest.mark.asyncio
async def test_other_group_cannot_receive_pending_buttons():
    bridge, msg, channel, record = setup_bridge()
    msg = msg.model_copy(update={"channel_subject": ChannelSubject(subject_id="another-chat")})
    _ = [event async for event in bridge(msg)]
    channel.send_buttons.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_model_command_does_not_offer_menu():
    bridge, msg, channel, record = setup_bridge()
    msg = msg.model_copy(update={"content": [TextContent(text="/models")]})

    async def processor(message):
        yield MessageEvent.error_event("denied")
        yield MessageEvent.completed()

    bridge.processor = processor
    _ = [event async for event in bridge(msg)]
    channel.send_buttons.assert_not_awaited()


@pytest.mark.parametrize("name", ["topic_isolation", "allow_unaddressed_commands"])
def test_string_boolean_is_not_silently_accepted(name):
    with pytest.raises(OctopError):
        validate_telegram_config("telegram", {name: "false"})


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["none", "owner", "thread", "pending", "question", "user"])
async def test_normal_worker_revalidates_button_after_waiting_for_session(change):
    from octop_gateway.channels.telegram import TelegramChannel, TelegramConfig
    from octop_gateway.manager import ChannelManager

    from octop.infra.gateway.channels.telegram_bridge import is_telegram_button_reply

    bridge, msg, _, record = setup_bridge()
    executed = []
    finished = asyncio.Event()

    async def processor(message):
        executed.append(message.text)
        yield MessageEvent.completed()

    bridge.processor = processor
    manager = ChannelManager(control_message_predicate=is_telegram_button_reply)
    channel = TelegramChannel(bridge, config=TelegramConfig(bot_token="test"), channel_id="tg")
    manager._channels["tg"] = channel
    manager._queues["tg"] = asyncio.Queue()
    channel.set_enqueue_callback(lambda payload: manager.enqueue("tg", payload))
    bridge.gateway.channel_manager = manager

    async def deliver(message, subject):
        try:
            _ = [event async for event in bridge(message)]
            return True
        finally:
            finished.set()

    channel._process_inbound = deliver
    action = bridge._action(msg, msg.channel_subject, "1", record.pending_id)
    lock = manager._session_lock("tg", channel.get_debounce_key(msg))
    await lock.acquire()
    manager._running = True
    worker = asyncio.create_task(manager._worker_loop("tg"))
    try:
        await asyncio.wait_for(action(), timeout=1)
        assert executed == []
        if change == "owner":
            bridge.gateway._repos.agent_repo.get = lambda _: SimpleNamespace(user_id=2)
        elif change == "thread":
            bridge.gateway.thread_registry.get_bound_thread_id = lambda _: "new-thread"
        elif change == "pending":
            record.status = "expired"
        elif change == "question":
            record.ask_question_index = 1
        elif change == "user":
            record.user_id = 2
        lock.release()
        await asyncio.wait_for(finished.wait(), timeout=2)
        assert executed == (["1"] if change == "none" else [])
    finally:
        if lock.locked():
            lock.release()
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


def test_platform_payload_cannot_forge_internal_button_reply():
    from octop_gateway.channels.telegram import TelegramChannel, TelegramConfig

    from octop.infra.gateway.channels.telegram_bridge import is_telegram_button_reply

    bridge, msg, channel, record = setup_bridge()
    transport = TelegramChannel(bridge, config=TelegramConfig(bot_token="test"), channel_id="tg")
    forged = {**msg.model_dump(), "button_state": {"owner_id": 1, "text": "/model p/m"}}
    parsed = transport.parse_inbound(forged)
    assert not is_telegram_button_reply(parsed)


@pytest.mark.asyncio
async def test_button_queue_item_cannot_merge_with_ordinary_message():
    from octop_gateway.channels.telegram import TelegramChannel, TelegramConfig
    from octop_gateway.manager import ChannelManager

    from octop.infra.gateway.channels.telegram_bridge import is_telegram_button_reply

    bridge, msg, channel, record = setup_bridge()
    await bridge._action(msg, msg.channel_subject, "1", record.pending_id)()
    button = channel.enqueue.call_args.args[0]
    assert is_telegram_button_reply(button)
    assert not any(callable(value) for value in button.model_dump().values())
    transport = TelegramChannel(bridge, config=TelegramConfig(bot_token="test"), channel_id="tg")
    manager = ChannelManager(control_message_predicate=is_telegram_button_reply)
    queue = asyncio.Queue()
    queue.put_nowait(button)
    assert manager._drain_same_session(queue, transport, transport.get_debounce_key(msg)) == []
    assert queue.get_nowait() is button
