"""Interactions topic-scope patch.

gateway compares ``topic`` strictly even when the callback was registered with
``None``. In groups the topic seen on the user's message and on the bot's own
message can differ (reply threads outside forum topics also carry a
``message_thread_id``), so a still-valid button gets rejected. A callback
registered without a topic now only has to match user and chat.

Callback TTL is not patched here: the bridge passes ``ttl`` to ``send_buttons``.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_MARK = "__octop_interaction_topic__"


def install() -> None:
    try:
        from octop_gateway.channels.telegram.interaction import Interactions
    except ImportError:  # gateway not installed
        return

    if getattr(Interactions.invoke, _MARK, False):
        return

    base_invoke = Interactions.invoke

    async def invoke(self, token, user, chat, topic):  # type: ignore[no-untyped-def]
        item = self.pending.get(token)
        if item is None:
            return False
        if item.expires < time.monotonic():
            self.pending.pop(token, None)
            return False
        if (item.user, item.chat) == (user, chat) and item.topic != topic:
            # 验证"回复链 thread id 让注册与回调 topic 对不上"的假设；仅在不一致时出现。
            logger.info(
                "telegram callback topic differs: chat=%s registered=%s actual=%s",
                chat,
                item.topic,
                topic,
            )
        # topic 为 None 时不参与比对：user 与 chat 仍严格校验。
        if item.topic is not None:
            return await base_invoke(self, token, user, chat, topic)
        if (item.user, item.chat) != (user, chat):
            return False
        self.pending.pop(token)
        await item.action()
        return True

    invoke.__octop_interaction_topic__ = True  # type: ignore[attr-defined]
    invoke.__wrapped_base__ = base_invoke  # type: ignore[attr-defined]
    Interactions.invoke = invoke  # type: ignore[method-assign]
