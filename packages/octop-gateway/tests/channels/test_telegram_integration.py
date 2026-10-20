"""Offline Telegram adapter integration: SDK payloads, mocked delivery and lifecycle."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Message, Update
from telegram.error import BadRequest, NetworkError, RetryAfter

from octop_gateway.channels.telegram.channel import TelegramChannel, TelegramConfig
from octop_gateway.channels.telegram.delivery import RequestScheduler, request
from octop_gateway.channels.telegram.interaction import Interactions
from octop_gateway.models import AudioContent, ChannelSubject, ImageContent, MessageEvent, TextContent


@pytest.fixture(autouse=True)
def fast_request_clock(monkeypatch):
    """Exercise request admission without real throttle sleeps."""

    def scheduler():
        now = [100.0]

        async def sleep(delay):
            now[0] += delay

        return RequestScheduler(clock=lambda: now[0], sleep=sleep)

    monkeypatch.setattr("octop_gateway.channels.telegram.channel.RequestScheduler", scheduler)


def sdk_message(mid=1, *, private=False, text="hello", **extra):
    return Message.de_json(
        {
            "message_id": mid,
            "date": 0,
            "chat": {"id": 42 if private else -42, "type": "private" if private else "supergroup"},
            "from": {"id": 7, "first_name": "User", "is_bot": False},
            "text": text,
            **extra,
        },
        None,
    )


async def noop(_message):
    yield MessageEvent.completed()


def channel(processor=noop, **config):
    result = TelegramChannel(processor, config=TelegramConfig(bot_token="secret", show_typing=False, **config))
    result._bot_id, result._bot_username = 99, "OurBot"
    result._app = SimpleNamespace(bot=MagicMock())
    for name in (
        "send_message",
        "edit_message_text",
        "send_message_draft",
        "edit_message_reply_markup",
        "send_photo",
        "send_video",
        "send_audio",
        "send_voice",
        "send_document",
        "send_media_group",
        "set_message_reaction",
        "get_file",
    ):
        setattr(result._app.bot, name, AsyncMock(return_value=SimpleNamespace(message_id=50)))
    return result


def subject(*, private=True, topic=None):
    return ChannelSubject(
        subject_id="42" if private else "-42",
        chat_type="direct" if private else "group",
        metadata={
            "chat_id": "42" if private else "-42",
            "user_id": "7",
            "message_thread_id": topic,
            "source_message_id": "1",
        },
    )


def inbound(ch, *, private=True, topic=None):
    return ch.parse_inbound(
        {
            "chat_id": "42" if private else "-42",
            "user_id": "7",
            "message_id": "1",
            "message_thread_id": topic,
            "is_group": not private,
            "content": [TextContent(text="hi")],
        }
    )


@pytest.mark.parametrize(
    "config", [{"allowed_user_ids": [8]}, {"allowed_chat_ids": [-43]}, {"group_activation": "mention"}]
)
async def test_admission_before_media_or_enqueue(config):
    ch = channel(**config)
    ch.enqueue = MagicMock()
    msg = sdk_message(text=None, photo=[{"file_id": "f", "file_unique_id": "u", "width": 1, "height": 1}])
    await ch._handle_update(Update(1, message=msg))
    ch.enqueue.assert_not_called()
    ch._app.bot.get_file.assert_not_called()
    assert not ch._files


async def test_dedup_edits_and_bounded_cache():
    ch = channel(edited_messages=True)
    ch.enqueue = MagicMock()
    await ch._handle_update(Update(1, message=sdk_message()))
    await ch._handle_update(Update(1, message=sdk_message()))
    await ch._handle_update(Update(2, edited_message=sdk_message(text="changed")))
    await ch._handle_update(Update(3, edited_message=sdk_message(2, text="/help")))
    await ch._handle_update(Update(4, edited_message=sdk_message(3, text="new edit")))
    assert ch.enqueue.call_count == 2
    assert ch.enqueue.call_args.args[0]["edited"]
    for index in range(1500):
        ch._is_duplicate(str(index))
    assert len(ch._seen_updates) == 1000
    assert len(ch._seen_messages) <= 1000


async def test_update_churn_cannot_evict_processed_message():
    ch = channel(edited_messages=True)
    ch.enqueue = MagicMock()
    await ch._handle_update(Update(1, message=sdk_message()))
    for index in range(2, 1200):
        await ch._handle_update(Update(index))
    await ch._handle_update(Update(1200, edited_message=sdk_message(text="changed")))
    ch.enqueue.assert_called_once()


async def test_message_dedup_has_independent_bounded_retention():
    ch = channel(edited_messages=True)
    ch.enqueue = MagicMock()
    for index in range(1, 1002):
        await ch._handle_update(Update(index, message=sdk_message(index)))
    assert len(ch._seen_messages) == 1000
    await ch._handle_update(Update(1002, edited_message=sdk_message(2, text="retained")))
    assert ch.enqueue.call_count == 1001
    await ch._handle_update(Update(1003, edited_message=sdk_message(1, text="evicted")))
    assert ch.enqueue.call_count == 1002


async def test_edits_disabled():
    ch = channel()
    ch.enqueue = MagicMock()
    await ch._handle_update(Update(1, edited_message=sdk_message()))
    ch.enqueue.assert_not_called()


async def test_internal_media_reference_and_download_sanitization():
    ch = channel()
    msg = sdk_message(text=None, photo=[{"file_id": "file-secret", "file_unique_id": "u", "width": 1, "height": 1}])
    native = await ch._build_message(msg)
    url = native["content"][0].url
    assert url.startswith("telegram-file://") and "secret" not in url
    ch._app.bot.get_file.assert_not_called()
    remote = SimpleNamespace(file_size=10, download_as_bytearray=AsyncMock(return_value=bytearray(b"photo")))
    ch._app.bot.get_file.return_value = remote
    assert (await ch.fetch_remote_media(url))[0] == b"photo"
    with pytest.raises(ValueError):
        await ch.fetch_remote_media("telegram-file://other/unknown")
    ch._app.bot.get_file.side_effect = NetworkError("https://api.telegram.org/botSECRET/file")
    with pytest.raises(RuntimeError, match=r"^Telegram media download failed$") as error:
        await ch.fetch_remote_media(url)
    assert error.value.__suppress_context__
    ch._app.bot.get_file.side_effect = None
    remote.file_size = 21 * 1024 * 1024
    with pytest.raises(ValueError, match="20 MB"):
        await ch.fetch_remote_media(url)


async def test_album_activation_and_sender_isolation():
    ch = channel(albums=True, group_activation="mention")
    ch.enqueue = MagicMock()
    photo = [{"file_id": "f", "file_unique_id": "u", "width": 1, "height": 1}]
    mention = {"type": "mention", "offset": 0, "length": 7}
    for index, fields in enumerate(
        [
            {"caption": "@OurBot", "caption_entities": [mention]},
            {},
            {"from": {"id": 8, "first_name": "Other", "is_bot": False}},
        ],
        1,
    ):
        await ch._handle_update(
            Update(index, message=sdk_message(index, text=None, photo=photo, media_group_id="album", **fields))
        )
    await asyncio.gather(*ch._album_tasks)
    ch.enqueue.assert_called_once()
    result = ch.enqueue.call_args.args[0]
    assert len(result["media"]) == 2
    assert result["user_id"] == "7"


async def test_passive_albums_do_not_reserve_active_slots():
    ch = channel(albums=True, group_activation="mention")
    ch.enqueue = MagicMock()
    photo = [{"file_id": "f", "file_unique_id": "u", "width": 1, "height": 1}]
    for index in range(1, 121):
        await ch._handle_update(
            Update(index, message=sdk_message(index, text=None, photo=photo, media_group_id=str(index)))
        )
    assert not ch._album_tasks
    assert len(ch._passive_albums) <= 100
    await ch._handle_update(
        Update(
            121,
            message=sdk_message(
                121,
                text=None,
                photo=photo,
                media_group_id="120",
                caption="@OurBot",
                caption_entities=[{"type": "mention", "offset": 0, "length": 7}],
            ),
        )
    )
    assert len(ch._album_tasks) == 1
    await asyncio.gather(*ch._album_tasks)
    ch.enqueue.assert_called_once()
    assert len(ch.enqueue.call_args.args[0]["media"]) == 2


async def test_passive_album_expiry_and_member_bounds():
    ch = channel(albums=True, group_activation="mention")
    photo = [{"file_id": "f", "file_unique_id": "u", "width": 1, "height": 1}]
    with patch("octop_gateway.channels.telegram.channel.time.monotonic", return_value=100):
        for index in range(1, 14):
            await ch._handle_update(
                Update(index, message=sdk_message(index, text=None, photo=photo, media_group_id="passive"))
            )
    assert max(len(items) for _, items in ch._passive_albums.values()) == 10
    with patch("octop_gateway.channels.telegram.channel.time.monotonic", return_value=101):
        await ch._handle_update(Update(14, message=sdk_message(14, text=None, photo=photo, media_group_id="new")))
    assert len(ch._passive_albums) == 1
    assert not ch._album_tasks


async def test_topic_subject_and_reply_options():
    ch = channel(topic_isolation=True, disable_notification=True, protect_content=True, link_preview=False)
    msg = inbound(ch, private=False, topic=12)
    assert msg.channel_subject.subject_id == "-42:topic:12"
    await ch._send_text(msg.channel_subject, "**bold**")
    kwargs = ch._app.bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == -42 and kwargs["message_thread_id"] == 12
    assert kwargs["reply_parameters"].message_id == 1
    assert kwargs["disable_notification"] and kwargs["protect_content"]
    assert kwargs["link_preview_options"].is_disabled
    assert kwargs["text"] == "<b>bold</b>"


async def test_long_html_and_plain_fallback():
    ch = channel()
    ch._app.bot.send_message.side_effect = [BadRequest("Can't parse entities"), SimpleNamespace(message_id=1)]
    await ch._send_text(subject(), "**bold**")
    assert ch._app.bot.send_message.call_args.kwargs["text"] == "bold"
    assert "parse_mode" not in ch._app.bot.send_message.call_args.kwargs
    ch._app.bot.send_message.reset_mock(side_effect=True)
    await ch._send_text(subject(), "**" + "😀" * 5000 + "**")
    assert ch._app.bot.send_message.call_count >= 3
    for call in ch._app.bot.send_message.call_args_list:
        assert call.kwargs["text"].startswith("<b>") and call.kwargs["text"].endswith("</b>")


@pytest.mark.parametrize("error", [NetworkError("ambiguous"), BadRequest("chat not found")])
async def test_no_ambiguous_or_nonformat_resends(error):
    ch = channel()
    ch._app.bot.send_message.side_effect = error
    with pytest.raises(type(error)):
        await ch._send_text(subject(), "hello")
    assert ch._app.bot.send_message.call_count == 1


async def test_retry_after_bounded_and_network_not_retried():
    method = AsyncMock(side_effect=[RetryAfter(0), RetryAfter(0), "ok"])
    with patch("octop_gateway.channels.telegram.delivery.asyncio.sleep", new_callable=AsyncMock) as sleep:
        assert await request(method, text="hello") == "ok"
        assert sleep.call_count == 2
    method = AsyncMock(side_effect=RetryAfter(0))
    with (
        patch("octop_gateway.channels.telegram.delivery.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(RetryAfter),
    ):
        await request(method)
    assert method.call_count == 3
    method = AsyncMock(side_effect=RetryAfter(31))
    with pytest.raises(RetryAfter):
        await request(method)
    assert method.call_count == 1


async def test_retry_after_rewinds_upload_stream():
    from io import BytesIO

    upload = BytesIO(b"photo bytes")
    received = []

    async def send(**kwargs):
        received.append(kwargs["photo"].read())
        if len(received) == 1:
            raise RetryAfter(0)

    with patch("octop_gateway.channels.telegram.delivery.asyncio.sleep", new_callable=AsyncMock):
        await request(send, photo=upload)
    assert received == [b"photo bytes", b"photo bytes"]


@pytest.mark.parametrize("handles", [False, True])
async def test_real_sdk_album_retry_preserves_multipart_bytes(handles):
    from io import BytesIO

    from telegram import Bot, InputFile, InputMediaPhoto, InputMediaVideo
    from telegram.request import HTTPXRequest

    uploads = [BytesIO(b"photo bytes"), BytesIO(b"video bytes"), BytesIO(b"thumbnail bytes")]
    files = [InputFile(stream, read_file_handle=not handles, attach=True) for stream in uploads]
    media = [InputMediaPhoto(files[0]), InputMediaVideo(files[1], thumbnail=files[2])]
    received = []

    async def consume(**kwargs):
        payload = kwargs["request_data"].multipart_data
        received.append([value.read() if hasattr(value, "read") else value for _, value, _ in payload.values()])
        return 429, b'{"ok":false,"error_code":429,"description":"Flood","parameters":{"retry_after":1}}'

    async with HTTPXRequest() as transport:
        bot = Bot("123456:fake-token", request=transport)
        with (
            patch.object(transport, "do_request", side_effect=consume),
            patch("octop_gateway.channels.telegram.delivery.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(RetryAfter),
        ):
            await request(bot.send_media_group, chat_id=42, media=media)
    assert received == [[b"photo bytes", b"video bytes", b"thumbnail bytes"]] * 3


async def test_unrecoverable_album_handle_is_not_retried():
    from io import BytesIO

    from telegram import InputFile, InputMediaPhoto

    class Unseekable(BytesIO):
        def tell(self):
            raise OSError("not seekable")

        def seek(self, *args):
            raise OSError("not seekable")

    media = [InputMediaPhoto(InputFile(Unseekable(b"bytes"), read_file_handle=False))]
    method = AsyncMock(side_effect=RetryAfter(0))
    with pytest.raises(RetryAfter):
        await request(method, media=media)
    method.assert_awaited_once()


async def test_handle_closed_by_first_attempt_prevents_retry():
    from io import BytesIO

    from telegram import InputFile, InputMediaPhoto

    stream = BytesIO(b"photo")
    media = [InputMediaPhoto(InputFile(stream, read_file_handle=False))]

    async def consume(**_kwargs):
        assert stream.read() == b"photo"
        stream.close()
        raise RetryAfter(0)

    method = AsyncMock(side_effect=consume)
    with pytest.raises(RetryAfter):
        await request(method, media=media)
    method.assert_awaited_once()


async def test_outbound_album_batches_and_voice():
    ch = channel(albums=True)
    await ch._send_content(subject(), [ImageContent(url=f"https://example.com/{i}.png") for i in range(12)])
    assert [len(call.kwargs["media"]) for call in ch._app.bot.send_media_group.call_args_list] == [10, 2]
    ch._config.audio_as_voice = True
    await ch._send_content(subject(), [AudioContent(url="https://example.com/audio.ogg")])
    ch._app.bot.send_voice.assert_awaited_once()
    ch._app.bot.send_media_group.side_effect = NetworkError("timeout")
    with pytest.raises(NetworkError):
        await ch._send_content(
            subject(), [ImageContent(url="https://example.com/a"), ImageContent(url="https://example.com/b")]
        )
    ch._app.bot.send_photo.assert_not_called()


@pytest.mark.parametrize(
    "mode,private,draft",
    [("draft", True, True), ("auto", True, True), ("auto", False, False), ("edit", True, False), ("off", True, False)],
)
async def test_stream_final_lifecycle(mode, private, draft):
    async def processor(_message):
        yield MessageEvent.delta("hello ")
        yield MessageEvent.delta("**world**")
        yield MessageEvent.completed()

    ch = channel(processor, streaming_mode=mode)
    msg = inbound(ch, private=private)
    assert await ch._process_inbound(msg, msg.channel_subject)
    bot = ch._app.bot
    if draft:
        assert bot.send_message_draft.call_count == 2
        assert bot.send_message_draft.call_args.kwargs["text"] == ""
        assert bot.send_message.call_args.kwargs["text"] == "hello <b>world</b>"
    elif mode != "off":
        bot.send_message.assert_awaited_once()
        assert bot.edit_message_text.call_args.kwargs["text"] == "hello <b>world</b>"
    else:
        bot.send_message_draft.assert_not_called()
        bot.edit_message_text.assert_not_called()
        bot.send_message.assert_awaited_once()
    assert not ch.interactions.pending and not ch._active


async def test_draft_rejection_falls_back_and_stream_flush():
    async def processor(_message):
        yield MessageEvent.delta("first")
        yield MessageEvent.flush()
        yield MessageEvent.delta("second")
        yield MessageEvent.completed()

    ch = channel(processor, streaming_mode="auto")
    ch._app.bot.send_message_draft.side_effect = BadRequest("unsupported")
    msg = inbound(ch)
    assert await ch._process_inbound(msg, msg.channel_subject)
    assert ch._app.bot.send_message.call_count == 2
    assert ch._app.bot.edit_message_text.call_args.kwargs["text"] == "second"


async def test_network_failure_does_not_duplicate_final():
    async def processor(_message):
        yield MessageEvent.delta("answer")
        yield MessageEvent.completed()

    ch = channel(processor, streaming_mode="edit")
    ch._app.bot.edit_message_text.side_effect = NetworkError("timeout")
    msg = inbound(ch)
    assert not await ch._process_inbound(msg, msg.channel_subject)
    assert ch._app.bot.send_message.call_count == 1
    assert ch._app.bot.edit_message_text.call_count == 1


async def test_stop_callback_scoped_and_worker_survives():
    entered = asyncio.Event()

    async def processor(_message):
        yield MessageEvent.delta("working")
        entered.set()
        await asyncio.Event().wait()
        yield MessageEvent.completed()

    ch = channel(processor, streaming_mode="edit")
    msg = inbound(ch, topic=4)
    worker = asyncio.create_task(ch._process_inbound(msg, msg.channel_subject))
    await entered.wait()
    token = next(iter(ch.interactions.pending))
    for user, chat, topic in [("8", "42", 4), ("7", "43", 4), ("7", "42", 5)]:
        assert not await ch.interactions.invoke(token, user, chat, topic)
        assert not worker.done()
    assert await ch.interactions.invoke(token, "7", "42", 4)
    assert await worker is False
    assert not worker.cancelled() and not ch._active and not ch.interactions.pending
    ch._original_processor = noop
    assert await ch._process_inbound(msg, msg.channel_subject)


@pytest.mark.parametrize("stop_button", [False, True])
async def test_queued_host_callback_returns_before_turn_and_stop_remains_responsive(stop_button):
    entered = asyncio.Event()

    async def processor(_message):
        yield MessageEvent.delta("working")
        entered.set()
        await asyncio.Event().wait()
        yield MessageEvent.completed()

    ch = channel(processor, streaming_mode="edit")
    queue = asyncio.Queue()
    ch.set_enqueue_callback(queue.put_nowait)
    native = {"chat_id": "42", "user_id": "7", "message_id": "1", "content": [TextContent(text="choice")]}

    async def action():
        ch.enqueue(native)

    token = ch.register_callback(subject(), action)

    def query_update(data):
        return SimpleNamespace(
            callback_query=SimpleNamespace(
                answer=AsyncMock(),
                data=data,
                from_user=SimpleNamespace(id=7),
                message=SimpleNamespace(chat=SimpleNamespace(id=42), message_thread_id=None),
            )
        )

    update = query_update(token)
    await asyncio.wait_for(ch._handle_callback(update), timeout=1)
    update.callback_query.answer.assert_awaited_once()
    assert not entered.is_set()
    msg = ch.parse_inbound(await queue.get())
    worker = asyncio.create_task(ch._process_inbound(msg, msg.channel_subject))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        if stop_button:
            stop_token = next(iter(ch.interactions.pending))
            await asyncio.wait_for(ch._handle_callback(query_update(stop_token)), timeout=1)
        else:
            await asyncio.wait_for(ch._handle_update(Update(2, message=sdk_message(2, private=True, text="/stop"))), 1)
        assert await asyncio.wait_for(worker, timeout=1) is False
        await ch._handle_callback(update)
        assert queue.empty()
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


async def test_external_worker_cancellation_propagates():
    entered = asyncio.Event()

    async def processor(_message):
        entered.set()
        await asyncio.Event().wait()
        yield MessageEvent.completed()

    ch = channel(processor)
    msg = inbound(ch)
    worker = asyncio.create_task(ch._process_inbound(msg, msg.channel_subject))
    await entered.wait()
    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker


async def test_callback_expiry_bounding_buttons_and_replay():
    interactions = Interactions()
    action = AsyncMock()
    expired = interactions.register("7", "42", None, action, ttl=-1)
    assert not await interactions.invoke(expired, "7", "42", None)
    for _ in range(1005):
        interactions.register("7", "42", None, action)
    assert len(interactions.pending) == 1000
    ch = channel()
    await ch.send_buttons(subject(), "Choose model", [("Model A", action)])
    token = ch._app.bot.send_message.call_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
    assert await ch.interactions.invoke(token, "7", "42", None)
    assert not await ch.interactions.invoke(token, "7", "42", None)
    action.assert_awaited_once()


async def test_start_caches_identity_and_registers_menu():
    ch = channel(command_menu=True, edited_messages=True)
    bot = SimpleNamespace(id=99, username="OurBot", set_my_commands=AsyncMock(), get_me=AsyncMock())
    app = MagicMock(bot=bot, initialize=AsyncMock(), start=AsyncMock(), stop=AsyncMock(), shutdown=AsyncMock())
    app.updater = SimpleNamespace(start_polling=AsyncMock(), running=False)
    builder = MagicMock()
    builder.token.return_value = builder
    builder.build.return_value = app
    with patch("telegram.ext.Application.builder", return_value=builder):
        await ch.start()
    assert (ch._bot_id, ch._bot_username) == (99, "OurBot")
    bot.get_me.assert_not_called()
    assert [command.command for command in bot.set_my_commands.call_args.kwargs["commands"]] == ["help", "stop"]
    assert "edited_message" in app.updater.start_polling.call_args.kwargs["allowed_updates"]
    await ch.stop()
    app.shutdown.assert_awaited_once()


async def test_ambiguous_preview_does_not_send_final_again():
    async def processor(_message):
        yield MessageEvent.delta("answer")
        yield MessageEvent.completed()

    ch = channel(processor, streaming_mode="edit")
    ch._app.bot.send_message.side_effect = NetworkError("ambiguous")
    msg = inbound(ch)
    await ch._process_inbound(msg, msg.channel_subject)
    assert ch._app.bot.send_message.call_count == 1


async def test_plaintext_fallback_timeout_is_not_replayed():
    async def processor(_message):
        yield MessageEvent.delta("**answer**")
        yield MessageEvent.completed()

    ch = channel(processor)
    ch._app.bot.send_message.side_effect = [BadRequest("Can't parse entities"), NetworkError("timeout")]
    msg = inbound(ch)
    assert not await ch._process_inbound(msg, msg.channel_subject)
    assert ch._app.bot.send_message.call_count == 2


async def test_stop_command_and_help_do_not_reach_processor():
    ch = channel()
    ch.enqueue = MagicMock()
    task = asyncio.create_task(asyncio.Event().wait())
    ch._active[("42", "7", None)] = task
    await ch._handle_update(Update(1, message=sdk_message(private=True, text="/stop")))
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    await ch._handle_update(Update(2, message=sdk_message(2, private=True, text="/help")))
    ch.enqueue.assert_not_called()
    assert "/stop" in ch._app.bot.send_message.call_args.kwargs["text"]


async def test_delta_then_identical_final_message_delivered_once():
    async def processor(_message):
        yield MessageEvent.delta("**answer**")
        yield MessageEvent.text("**answer**")
        yield MessageEvent.completed()

    ch = channel(processor, streaming_mode="edit")
    msg = inbound(ch)
    assert await ch._process_inbound(msg, msg.channel_subject)
    ch._app.bot.send_message.assert_awaited_once()
    assert ch._app.bot.edit_message_text.call_args.kwargs["text"] == "<b>answer</b>"


async def test_sdk_delivery_error_does_not_leak_credentials(caplog):
    async def processor(_message):
        yield MessageEvent.delta("answer")
        yield MessageEvent.completed()

    ch = channel(processor)
    ch._app.bot.send_message.side_effect = NetworkError("https://api.telegram.org/botSECRET/sendMessage")
    msg = inbound(ch)
    assert not await ch._process_inbound(msg, msg.channel_subject)
    assert "SECRET" not in caplog.text


async def test_rejected_album_members_are_not_buffered():
    ch = channel(albums=True, allowed_user_ids=[8])
    msg = sdk_message(
        text=None,
        photo=[{"file_id": "f", "file_unique_id": "u", "width": 1, "height": 1}],
        media_group_id="album",
    )
    await ch._handle_update(Update(1, message=msg))
    buffered = bool(ch._albums)
    await asyncio.gather(*ch._album_tasks)
    assert not buffered


async def test_media_options_match_sdk_signatures():
    import inspect

    from telegram import Bot

    ch = channel(albums=True, protect_content=True, disable_notification=True)
    target = subject(private=False, topic=12)
    await ch._send_media(target, ImageContent(url="https://example.com/a.png"))
    await ch._send_content(
        target, [ImageContent(url="https://example.com/a.png"), ImageContent(url="https://example.com/b.png")]
    )
    for name in ("send_photo", "send_media_group"):
        kwargs = getattr(ch._app.bot, name).call_args.kwargs
        inspect.signature(getattr(Bot, name)).bind(ch._app.bot, **kwargs)
        assert "link_preview_options" not in kwargs
        assert kwargs["message_thread_id"] == 12
        assert kwargs["reply_parameters"].message_id == 1


async def test_reactions_and_upload_preflight_marker():
    ch = channel(status_reactions=True, albums=True)
    msg = inbound(ch)
    assert await ch._process_inbound(msg, msg.channel_subject)
    assert [call.kwargs["reaction"] for call in ch._app.bot.set_message_reaction.call_args_list] == ["👀", "👍"]
    ch.load_media_bytes = AsyncMock(side_effect=ValueError("missing"))
    await ch._send_content(subject(), [ImageContent(data="eA=="), ImageContent(data="eA==")])
    assert ch._app.bot.send_message.call_count == 2
    assert "upload unavailable" in ch._app.bot.send_message.call_args.kwargs["text"]
    ch._app.bot.send_media_group.assert_not_called()


async def test_scheduler_bot_chat_bounds_and_cancel():
    now = [100.0]
    calls = []

    async def sleep(delay):
        calls.append(delay)
        now[0] += delay

    scheduler = RequestScheduler(clock=lambda: now[0], sleep=sleep, max_chats=2)
    await scheduler.acquire(1)
    await scheduler.acquire(2)
    assert now[0] == pytest.approx(100 + 1 / 30)
    await scheduler.acquire(3)
    assert now[0] >= 101
    assert len(scheduler._chats) <= 2
    await scheduler.acquire(3)
    assert now[0] >= 102
    assert calls

    async def cancelled(_delay):
        raise asyncio.CancelledError

    scheduler._sleep = cancelled
    reserved = dict(scheduler._chats)
    with pytest.raises(asyncio.CancelledError):
        await scheduler.acquire(3)
    assert dict(scheduler._chats) == reserved
    assert not scheduler._lock.locked()


async def test_every_attempt_scheduled_and_base_slot_once():
    ch = channel(albums=True, streaming_mode="edit")
    ch._requests.acquire = AsyncMock()
    ch._acquire_rate_slot = AsyncMock()
    ch._app.bot.send_message.side_effect = [
        RetryAfter(0),
        SimpleNamespace(message_id=50),
        SimpleNamespace(message_id=51),
    ]
    with patch("octop_gateway.channels.telegram.delivery.asyncio.sleep", new_callable=AsyncMock):
        await ch.reply_text(subject(), "x" * 5000)
    ch._acquire_rate_slot.assert_awaited_once()
    assert ch._requests.acquire.await_count == 3
    ch._app.bot.send_message.side_effect = None
    await ch.send_buttons(subject(), "Model", [("A", AsyncMock())])
    await ch._send_content(subject(), [ImageContent(url="https://example.com/a")] * 2)
    state = {"text": "preview", "last": 0, "draft_id": 1}
    await ch._preview(subject(), state)
    await ch._finish_preview(subject(), "final", state)
    assert ch._requests.acquire.await_count == 7
    ch._acquire_rate_slot.assert_awaited_once()


@pytest.mark.parametrize("mode", ["off", "edit", "draft"])
async def test_revised_final_replaces_deltas_with_attachments(mode):
    async def processor(_message):
        yield MessageEvent.delta("old answer")
        yield MessageEvent(
            type="message", content=[TextContent(text="revised answer"), ImageContent(url="https://example.com/a")]
        )
        yield MessageEvent.completed()

    ch = channel(processor, streaming_mode=mode)
    msg = inbound(ch)
    assert await ch._process_inbound(msg, msg.channel_subject)
    if mode == "edit":
        assert ch._app.bot.edit_message_text.call_args.kwargs["text"] == "revised answer"
    else:
        assert ch._app.bot.send_message.call_args.kwargs["text"] == "revised answer"
    ch._app.bot.send_message.assert_awaited_once()
    ch._app.bot.send_photo.assert_awaited_once()


async def test_album_bounds_and_late_window():
    ch = channel(albums=True)
    ch.enqueue = MagicMock()
    gate = asyncio.Event()

    async def wait(_delay):
        await gate.wait()

    photo = [{"file_id": "f", "file_unique_id": "u", "width": 1, "height": 1}]

    def member(mid, group):
        return Update(mid, message=sdk_message(mid, text=None, photo=photo, media_group_id=group))

    with patch("octop_gateway.channels.telegram.channel.asyncio.sleep", side_effect=wait):
        for index in range(1, 113):
            await ch._handle_update(member(index, "first" if index <= 12 else str(index)))
        assert len(ch._album_tasks) == 100
        assert len(ch._albums) == 100
        assert max(map(len, ch._albums.values())) == 10
        gate.set()
        await asyncio.gather(*ch._album_tasks)
        assert not ch._albums
        before = ch.enqueue.call_count
        await ch._handle_update(member(113, "first"))
        await asyncio.gather(*ch._album_tasks)
        assert ch.enqueue.call_count == before + 1
        await ch._handle_update(member(113, "first"))
        assert not ch._albums


async def test_start_and_callback_errors_sanitized_without_swallowing():
    ch = channel()
    builder = MagicMock()
    builder.token.return_value = builder
    builder.build.return_value.initialize = AsyncMock(
        side_effect=NetworkError("https://api.telegram.org/botSECRET/getMe")
    )
    with patch("telegram.ext.Application.builder", return_value=builder), pytest.raises(NetworkError) as caught:
        await ch.start()
    assert "SECRET" not in str(caught.value) and caught.value.__suppress_context__
    query = SimpleNamespace(answer=AsyncMock(side_effect=NetworkError("https://api.telegram.org/botSECRET/answer")))
    with pytest.raises(NetworkError) as caught:
        await ch._handle_callback(SimpleNamespace(callback_query=query))
    assert "SECRET" not in str(caught.value)
    query.answer.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await ch._handle_callback(SimpleNamespace(callback_query=query))
    query.answer.side_effect = ValueError("host error")
    with pytest.raises(ValueError, match="host error"):
        await ch._handle_callback(SimpleNamespace(callback_query=query))
