"""Telegram 按钮选择后的收尾交互。

现有行为：点击选项只有空应答（无 toast 文案），按钮列表永远展开。
本补丁在成功选择后：toast 显示所选，并把原消息收尾——附加所选标注并
移除内联键盘（分页箭头只移除键盘；Stop 按钮交给流式预览自己的清理，
避免编辑竞争）。选择失效时 toast 提示并同样收起键盘，防止僵尸按钮。
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

logger = logging.getLogger(__name__)

_MARK = "__octop_button_ux__"
_PAGE_LABELS = frozenset({"←", "→"})
_STOP_LABEL = "Stop"
_EXPIRED_NOTE = "该选择已失效或已处理"


def _clicked_label(query: Any) -> str:
    """从消息键盘里找出被点击按钮的文案。"""
    try:
        for row in query.message.reply_markup.inline_keyboard:
            for button in row:
                if button.callback_data == query.data:
                    return str(button.text)
    except Exception:  # noqa: BLE001 结构缺失时无标注，不影响收尾
        pass
    return ""


def install() -> None:
    """包裹 TelegramChannel._handle_callback；重复调用安全。"""
    try:
        from octop_gateway.channels.telegram.channel import TelegramChannel
        from octop_gateway.channels.telegram.delivery import sanitized_errors
        from telegram.error import TelegramError
    except ImportError:  # gateway 未安装时静默跳过
        return

    if getattr(TelegramChannel._handle_callback, _MARK, False):
        return

    async def handle_callback(self, update, _context=None):  # type: ignore[no-untyped-def]  noqa: ANN001
        query = update.callback_query
        if not query:
            return
        label = _clicked_label(query)
        if not query.message or not query.from_user:
            await self._request(query.answer)
            return
        invoked = False
        async with sanitized_errors():
            invoked = await self.interactions.invoke(
                query.data or "",
                str(query.from_user.id),
                str(query.message.chat.id),
                getattr(query.message, "message_thread_id", None),
            )
        note = (f"✓ {label}" if label else "✓") if invoked else _EXPIRED_NOTE
        with suppress(TelegramError):
            await self._request(query.answer, text=note)
        if label == _STOP_LABEL:
            # 流式预览消息由 run() 的 finally 清理，避免编辑竞争
            return
        try:
            if label in _PAGE_LABELS or not query.message.text:
                await self._request(
                    self._app.bot.edit_message_reply_markup,
                    chat_id=query.message.chat.id,
                    message_id=query.message.message_id,
                    reply_markup=None,
                )
            else:
                await self._request(
                    self._app.bot.edit_message_text,
                    chat_id=query.message.chat.id,
                    message_id=query.message.message_id,
                    text=f"{query.message.text}\n{note}",
                )
        except TelegramError:
            logger.debug("choice message settle unavailable")

    handle_callback.__octop_button_ux__ = True  # type: ignore[attr-defined]
    TelegramChannel._handle_callback = handle_callback  # type: ignore[method-assign]
