"""Native rich-table delivery for Telegram (edit-in-place, options, fallbacks)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from octop_gateway.channels.telegram.channel import TelegramChannel
from telegram.error import BadRequest, NetworkError

import octop.infra.gateway.channels.telegram_table_format as ttf

TABLE = "| name | value |" + chr(10) + "|---|---|" + chr(10) + "| cpu | 80% |"
SUBJECT = SimpleNamespace(subject_id="555", metadata={"chat_id": "555"}, chat_type="group")


@pytest.fixture(autouse=True)
def _install():
    ttf.install()
    yield


class _Bot:
    def __init__(self, error: Exception | None = None) -> None:
        self.rich: list[dict] = []
        self.edits: list[dict] = []
        self.error = error
        self.send_message = AsyncMock(return_value=SimpleNamespace(message_id=1))
        self.edit_message_text = AsyncMock(return_value=True)

    async def _post(self, endpoint, data):
        if self.error is not None:
            raise self.error
        if endpoint == "editMessageText":
            self.edits.append(data)
        else:
            self.rich.append(data)
        return {"message_id": 1}


def _channel(preview_message_id, *, error: Exception | None = None, finalizing: bool = True):
    ch = TelegramChannel.__new__(TelegramChannel)
    ch._app = SimpleNamespace(bot=_Bot(error))
    state = {"message_id": preview_message_id} if preview_message_id else {}
    ch._state = state
    ch._stream = SimpleNamespace(get=lambda: state or None)
    ch._config = SimpleNamespace(
        link_preview=True, disable_notification=False, protect_content=False, reply_to_message=False
    )

    async def request(method, **kwargs):
        # rich 投递经 _request 调度；其余调用（回退路径）只记录。
        if "endpoint" in kwargs:
            return await method(**kwargs)
        return None

    ch._request = AsyncMock(side_effect=request)
    ch._clean_output = lambda text: text
    ch.interactions = SimpleNamespace(pending={})
    if preview_message_id:
        state.update(text=TABLE, finalizing=finalizing, stop_token=None, draft_sent=False)
        ch._finish_preview = AsyncMock()
    return ch


def _fallback_calls(ch):
    return [c for c in ch._request.await_args_list if "endpoint" not in c.kwargs]


@pytest.mark.asyncio
async def test_group_preview_placeholder_is_edited_into_rich_table():
    """群聊无 draft：占位消息必须原地编辑成原生表格，既不重复也不退化成代码块。"""
    ch = _channel(preview_message_id=99)
    await TelegramChannel._send_text(ch, SUBJECT, TABLE)
    assert len(ch._app.bot.edits) == 1, "must edit the placeholder in place"
    edit = ch._app.bot.edits[0]
    assert edit["message_id"] == 99
    assert edit["rich_message"]["markdown"] == TABLE
    assert ch._app.bot.rich == [], "must not send a second rich message"
    assert _fallback_calls(ch) == []


@pytest.mark.asyncio
async def test_in_place_edit_releases_preview_state():
    """编辑成功后必须像 _finish_preview 一样放手预览消息，否则下一段会覆盖表格。"""
    ch = _channel(preview_message_id=99)
    ch._state["stop_token"] = "tok"
    ch.interactions.pending["tok"] = object()
    await TelegramChannel._send_text(ch, SUBJECT, TABLE)
    assert "message_id" not in ch._state
    assert ch._state["finalizing"] is False
    assert ch.interactions.pending == {}
    # 同一轮的下一个表格段落不再命中旧消息，而是新发。
    ch._state.update(text=TABLE, finalizing=True)
    await TelegramChannel._send_text(ch, SUBJECT, TABLE)
    assert len(ch._app.bot.edits) == 1
    assert len(ch._app.bot.rich) == 1


@pytest.mark.asyncio
async def test_preview_not_finalizing_sends_new_rich_message():
    """非收尾阶段的 send_text 不能编辑预览消息。"""
    ch = _channel(preview_message_id=99, finalizing=False)
    await TelegramChannel._send_text(ch, SUBJECT, TABLE)
    assert ch._app.bot.edits == []
    assert len(ch._app.bot.rich) == 1


@pytest.mark.asyncio
async def test_rich_table_sent_when_no_preview():
    ch = _channel(preview_message_id=None)
    await TelegramChannel._send_text(ch, SUBJECT, TABLE)
    assert len(ch._app.bot.rich) == 1
    assert ch._app.bot.rich[0]["rich_message"]["markdown"] == TABLE
    assert _fallback_calls(ch) == []


@pytest.mark.asyncio
async def test_rich_table_keeps_topic_and_reply_options():
    """sendRichMessage 必须带话题/回复/静默配置，否则论坛话题里的表格会落到 General。"""
    ch = _channel(preview_message_id=None)
    ch._config.reply_to_message = True
    ch._config.protect_content = True
    subject = SimpleNamespace(
        subject_id="555",
        chat_type="group",
        metadata={"chat_id": "555", "message_thread_id": 9, "source_message_id": "41"},
    )
    await TelegramChannel._send_text(ch, subject, TABLE)
    data = ch._app.bot.rich[0]
    assert data["message_thread_id"] == 9
    assert data["reply_parameters"].message_id == 41
    assert data["protect_content"] is True


@pytest.mark.asyncio
async def test_rich_rejection_falls_back_to_code_block():
    ch = _channel(preview_message_id=None, error=BadRequest("rich unsupported"))
    await TelegramChannel._send_text(ch, SUBJECT, TABLE)
    html = _fallback_calls(ch)[0].kwargs["text"]
    assert "|---|" not in html, "fallback must render an aligned table, not raw pipes"


@pytest.mark.asyncio
async def test_rich_ambiguous_network_error_is_not_resent():
    """超时可能已送达：不得回退重发，沿用 gateway 的 delivery_failed 约定。"""
    ch = _channel(preview_message_id=None, error=NetworkError("timeout"))
    state = ch._state
    ch._stream = SimpleNamespace(get=lambda: state)
    with pytest.raises(NetworkError):
        await TelegramChannel._send_text(ch, SUBJECT, TABLE)
    assert state["delivery_failed"] is True
    assert _fallback_calls(ch) == []


@pytest.mark.asyncio
async def test_plain_text_bypasses_rich():
    ch = _channel(preview_message_id=None)
    await TelegramChannel._send_text(ch, SUBJECT, "no table here")
    assert ch._app.bot.rich == []
    assert len(_fallback_calls(ch)) == 1
