"""tests/unit/i18n/test_channel.py"""

from __future__ import annotations

from octop.i18n import channel_tool_hint_end, channel_tool_hint_start
from octop.i18n.domains.channel import telegram_quote_prompt, telegram_reject_notice


def test_channel_tool_hint_start_zh():
    text = channel_tool_hint_start("读取文件", "zh")
    assert text.startswith("🔧")
    assert "正在调用工具" in text
    assert "读取文件" in text


def test_channel_tool_hint_end_en():
    assert channel_tool_hint_end("Read file", "en") == "✅ Read file done"


def test_telegram_reject_notice_known_and_unknown_reason():
    assert telegram_reject_notice("user_mismatch", "zh") == "该卡片不属于当前会话"
    assert telegram_reject_notice("pending_expired_or_resolved", "en").startswith("This card")
    assert telegram_reject_notice("brand_new_reason", "en") == (
        "The action did not take effect. Please try again."
    )
    assert telegram_reject_notice("brand_new_reason", "zh") == "操作未生效，请重试"


def test_telegram_quote_prompt_locales():
    assert telegram_quote_prompt("hi", "en") == "[Quoted message]\nhi\n\n[Current message]\n"
    assert telegram_quote_prompt("hi", "zh") == "[引用消息]\nhi\n\n[当前消息]\n"
