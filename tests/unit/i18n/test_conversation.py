"""tests/unit/i18n/test_conversation.py — Ask/Plan/Craft hint key parity (#616 M7)."""

from __future__ import annotations

from octop.i18n import all_keys_for_locale, tr
from octop.i18n.domains.conversation import conversation_mode_system_hint


def test_conversation_mode_keys_parity() -> None:
    en_keys = {k for k in all_keys_for_locale("en") if k.startswith("conversation.")}
    zh_keys = {k for k in all_keys_for_locale("zh") if k.startswith("conversation.")}
    assert en_keys == zh_keys
    for mode in ("ask", "plan", "craft"):
        key = f"conversation.mode.{mode}_system_hint"
        assert key in en_keys
        assert tr(key, "en")
        assert tr(key, "zh")


def test_conversation_mode_system_hint_helper() -> None:
    ask_en = conversation_mode_system_hint("ask", "en")
    ask_zh = conversation_mode_system_hint("ask", "zh")
    assert "Ask" in ask_en or "read-only" in ask_en or "Ask mode" in ask_en
    assert "仅问答" in ask_zh
    assert ask_en != ask_zh
    plan_en = conversation_mode_system_hint("plan", "en")
    assert "task" in plan_en.lower() or "ACP" in plan_en or "delegate" in plan_en.lower()


def test_conversation_mode_tool_blocked_helper() -> None:
    from octop.i18n.domains.conversation import conversation_mode_tool_blocked

    en = conversation_mode_tool_blocked("execute", "ask", "en")
    zh = conversation_mode_tool_blocked("execute", "ask", "zh")
    assert "execute" in en
    assert "execute" in zh
    assert en != zh


def test_conversation_mode_plan_brief_block() -> None:
    from octop.i18n.domains.conversation import conversation_mode_plan_brief_block

    en = conversation_mode_plan_brief_block("## Approved plan\n\nDo it.", "en")
    zh = conversation_mode_plan_brief_block("## Approved plan\n\nDo it.", "zh")
    assert "Approved plan" in en
    assert "Do it." in en
    assert en != zh or "计划" in zh or "确认" in zh


def test_plan_ready_cta_keys_parity() -> None:
    """Backend keeps mode system hints; dashboard owns Ready-to-build CTA copy."""
    for mode in ("ask", "plan", "craft"):
        assert tr(f"conversation.mode.{mode}_system_hint", "en")
        assert tr(f"conversation.mode.{mode}_system_hint", "zh")
    assert tr("conversation.mode.tool_blocked", "en", tool_name="x", mode="ask")
    assert tr("conversation.mode.tool_blocked", "zh", tool_name="x", mode="ask")
    assert tr("conversation.mode.plan_brief_prefix", "en")
    assert tr("conversation.mode.plan_brief_prefix", "zh")
