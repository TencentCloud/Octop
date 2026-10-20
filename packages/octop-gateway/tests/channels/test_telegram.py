"""Unit tests for Telegram channel."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Message

from octop_gateway.channels.telegram import TelegramChannel, TelegramConfig
from octop_gateway.channels.telegram.format_html import markdown_to_telegram_html
from octop_gateway.models import InboundMessage, MessageEvent, TextContent


async def _noop_processor(msg: InboundMessage):
    yield MessageEvent.completed()


class TestTelegramChannelUnit:
    def test_config_display_flags(self) -> None:
        config = TelegramConfig(bot_token="token", show_tool_hints=False, show_thinking=True)
        ch = TelegramChannel(processor=_noop_processor, config=config)
        assert ch.channel_type == "telegram"
        assert ch.constraints.show_tool_hints is False
        assert ch.constraints.show_thinking is True

    def test_parse_inbound(self) -> None:
        ch = TelegramChannel(processor=_noop_processor, config=TelegramConfig(bot_token="token"))
        msg = ch.parse_inbound(
            {
                "chat_id": "12345",
                "user_id": "67890",
                "message_id": "99",
                "is_group": False,
                "content": [TextContent(text="hi telegram")],
            }
        )
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "12345"
        assert msg.metadata["user_id"] == "67890"
        assert msg.content[0].text == "hi telegram"  # type: ignore[union-attr]

    def test_markdown_to_html(self) -> None:
        html = markdown_to_telegram_html("**bold** and `code`")
        assert "<b>bold</b>" in html
        assert "<code>code</code>" in html


class TestTelegramAllowedUsers:
    @staticmethod
    def _message(user_id: int | None) -> SimpleNamespace:
        user = SimpleNamespace(id=user_id) if user_id is not None else None
        return SimpleNamespace(from_user=user, chat=SimpleNamespace(id=-100123, type="supergroup"))

    def test_empty_allowlist_keeps_bot_open(self) -> None:
        ch = TelegramChannel(processor=_noop_processor, config=TelegramConfig(bot_token="t"))
        assert ch._is_allowed_sender(self._message(42)) is True
        assert ch._is_allowed_sender(self._message(None)) is True

    def test_allowlist_filters_senders(self) -> None:
        cfg = TelegramConfig(bot_token="t", allowed_user_ids=["42"])
        ch = TelegramChannel(processor=_noop_processor, config=cfg)
        assert ch._is_allowed_sender(self._message(42)) is True
        assert ch._is_allowed_sender(self._message(7)) is False
        assert ch._is_allowed_sender(self._message(None)) is False

    def test_from_dict_parses_ids(self) -> None:
        cfg = TelegramConfig.from_dict({"bot_token": " t ", "allowed_user_ids": "42, 43\n42"})
        assert cfg.bot_token == "t"
        assert cfg.allowed_user_ids == ["42", "43"]
        assert TelegramConfig.from_dict({"bot_token": "t", "allowed_user_ids": [42, "43"]}).allowed_user_ids == [
            "42",
            "43",
        ]
        assert TelegramConfig.from_dict({"bot_token": "t", "allowed_user_ids": ""}).allowed_user_ids == []
        assert TelegramConfig.from_dict({"bot_token": "t"}).allowed_user_ids == []

    def test_from_dict_rejects_non_numeric_ids(self) -> None:
        with pytest.raises(ValueError, match="allowed_user_ids"):
            TelegramConfig.from_dict({"bot_token": "t", "allowed_user_ids": "@username"})

    async def test_blocked_sender_never_reaches_processor(self) -> None:
        cfg = TelegramConfig(bot_token="t", allowed_user_ids=["42"])
        ch = TelegramChannel(processor=_noop_processor, config=cfg)
        handlers: list = []
        app = MagicMock()
        app.add_handler.side_effect = lambda h: handlers.append(h)
        app.initialize = AsyncMock()
        app.start = AsyncMock()
        app.updater = None
        builder = MagicMock()
        builder.token.return_value.build.return_value = app
        with patch("telegram.ext.Application.builder", return_value=builder):
            await ch.start()
        enqueued: list = []
        ch.enqueue = enqueued.append  # type: ignore[method-assign]
        callback = handlers[0].callback

        def update(user_id: int) -> SimpleNamespace:
            msg = Message.de_json(
                {
                    "from": {"id": user_id, "first_name": "User", "is_bot": False},
                    "chat": {"id": user_id, "type": "private"},
                    "text": "hi",
                    "message_id": 1,
                    "date": 0,
                },
                None,
            )
            return SimpleNamespace(message=msg, edited_message=None)

        await callback(update(7), None)
        assert enqueued == []
        await callback(update(42), None)
        assert len(enqueued) == 1
        assert enqueued[0]["user_id"] == "42"
