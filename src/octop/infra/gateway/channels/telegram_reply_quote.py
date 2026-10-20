"""Telegram reply-quote plumbing.

Two gaps stop agents from seeing what a user replied to:

1. ``_extract_message`` only forwards ``reply_to_message_id``; the quoted body
   is never read.
2. ``parse_inbound`` rebuilds metadata from a hard-coded whitelist, so even
   after (1) adds fields they are dropped before reaching the host.

Both are wrapped here. ``_extract_message`` is async and ``parse_inbound`` is
sync; the wrappers must preserve that or callers await a coroutine object.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MARK_EXTRACT = "__octop_telegram_reply_quote__"
_MARK_PARSE = "__octop_telegram_reply_quote_parse__"
# parse_inbound 只透传这些键；不能按"白名单外全部透传"，否则 content 等整份载荷会进 metadata。
_PASSTHROUGH_KEYS = ("reply_to_text", "reply_quote_text")
# 被引正文进入提示词前截断，避免回复长消息时提示词膨胀。
_MAX_QUOTE_CHARS = 2000


def _log_non_topic_thread(message) -> None:  # type: ignore[no-untyped-def]
    """记录普通（非论坛话题）群消息上出现的 message_thread_id。

    Telegram 文档里 message_thread_id 同时表示"消息线程"与"论坛话题"，只有
    is_topic_message 能区分。gateway 目前直接拿它做 topic，这条日志用来确认
    普通超级群的回复链是否带该字段；只在该异常组合出现时打印。
    """
    thread_id = getattr(message, "message_thread_id", None)
    chat = getattr(message, "chat", None)
    if (
        thread_id is not None
        and getattr(chat, "type", "") in ("group", "supergroup")
        and not getattr(message, "is_topic_message", False)
    ):
        logger.info(
            "telegram non-topic group message carries thread id: chat=%s thread=%s message=%s",
            getattr(chat, "id", None),
            thread_id,
            getattr(message, "message_id", None),
        )


def install() -> None:
    """Wrap the extractor and parser; safe to call twice."""
    try:
        from octop_gateway.channels.telegram.channel import TelegramChannel
    except ImportError:  # gateway not installed
        return

    _wrap_extract(TelegramChannel)
    _wrap_parse(TelegramChannel)


def _wrap_extract(channel_cls) -> None:  # type: ignore[no-untyped-def]
    base = channel_cls._extract_message
    if getattr(base, _MARK_EXTRACT, False):
        return

    async def _extract_message(self, message, *args, **kwargs):  # type: ignore[no-untyped-def]
        # 原方法是 async def，包装必须保持异步；否则调用方 await 到的是协程对象而非 dict，
        # 会触发 coroutine never awaited 并让整条消息链路静默瘫痪。
        data = await base(self, message, *args, **kwargs)
        if data is None:
            return None
        _log_non_topic_thread(message)
        reply = getattr(message, "reply_to_message", None)
        reply_from = getattr(reply, "from_user", None)
        # 回复 bot 自己的消息时，被引正文就是 agent 上一条输出，已在会话历史里。
        own_reply = reply_from is not None and reply_from.id == getattr(self, "_bot_id", None)
        text = None
        if reply is not None and not own_reply:
            text = getattr(reply, "text", None) or getattr(reply, "caption", None)
        quote = getattr(getattr(message, "quote", None), "text", None)
        data["reply_to_text"] = text[:_MAX_QUOTE_CHARS] if text else None
        data["reply_quote_text"] = quote[:_MAX_QUOTE_CHARS] if quote else None
        return data

    _extract_message.__octop_telegram_reply_quote__ = True  # type: ignore[attr-defined]
    _extract_message.__wrapped_base__ = base  # type: ignore[attr-defined]
    channel_cls._extract_message = _extract_message


def _wrap_parse(channel_cls) -> None:  # type: ignore[no-untyped-def]
    base = channel_cls.parse_inbound
    if getattr(base, _MARK_PARSE, False):
        return

    def parse_inbound(self, raw_payload, *args, **kwargs):  # type: ignore[no-untyped-def]
        # 原方法是同步的（非 async def），包装必须保持同步。
        message = base(self, raw_payload, *args, **kwargs)
        if not isinstance(raw_payload, dict):
            return message
        # 引用正文不在 gateway 的 metadata 白名单内，这里按键显式透传。
        extra = {
            key: raw_payload[key]
            for key in _PASSTHROUGH_KEYS
            if raw_payload.get(key) and key not in message.metadata
        }
        if not extra:
            return message
        message.metadata.update(extra)
        if message.channel_subject is not None:
            message.channel_subject.metadata.update(extra)
        return message

    parse_inbound.__octop_telegram_reply_quote_parse__ = True  # type: ignore[attr-defined]
    parse_inbound.__wrapped_base__ = base  # type: ignore[attr-defined]
    channel_cls.parse_inbound = parse_inbound
