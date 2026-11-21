"""Whole-message IM approval phrases."""

from __future__ import annotations

from octop.infra.gateway.hitl.phrases import ApprovalPhraseKind, match_approval_utterance


def _kind(text: str) -> ApprovalPhraseKind | None:
    match = match_approval_utterance(text)
    return None if match is None else match.kind


def test_match_approval_utterance_exact_phrases() -> None:
    assert _kind("同意") == "once"
    assert _kind("同意。") == "once"
    assert _kind("「允许」") == "once"
    assert _kind("  Approve  ") == "once"
    assert _kind("放通这个工具") == "tool"
    assert _kind("这个工具以后都允许") == "tool"
    assert _kind("allow this tool") == "tool"
    assert _kind("都不用问了") == "all"
    assert _kind("ALLOW ALL") == "all"
    assert _kind("不允许") == "reject"
    assert _kind("Reject") == "reject"
    assert _kind("恢复每次审批") == "reset"
    assert _kind("ask again") == "reset"


def test_match_approval_utterance_rejects_ordinary_text() -> None:
    assert match_approval_utterance("可以") is None
    assert match_approval_utterance("好的") is None
    assert match_approval_utterance("行") is None
    assert match_approval_utterance("同意，然后继续查日志") is None
    assert match_approval_utterance("我觉得可以先看看") is None
    assert match_approval_utterance("批准一下") is None
    assert match_approval_utterance("") is None
    assert match_approval_utterance(None) is None
