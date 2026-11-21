"""Whole-message replies that decide a pending IM tool approval.

Matching is exact after trimming whitespace and surrounding punctuation.
A longer sentence is ordinary chat, even if it contains one of these words.
Short replies such as "可以" / "好的" / "行" are intentionally absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ApprovalPhraseKind = Literal["once", "tool", "all", "reject", "reset"]

_ONCE = ("批准", "同意", "允许", "approve")
_TOOL = ("这个工具以后都允许", "放通这个工具", "allow this tool")
_ALL = ("本对话都允许", "都不用问了", "allow all")
_REJECT = ("拒绝", "不允许", "reject")
_RESET = ("恢复每次审批", "ask again")

_EDGE = "。．.!！?？,，、;；:：\"'“”‘’「」『』()（）[]【】"


@dataclass(frozen=True)
class ApprovalUtterance:
    kind: ApprovalPhraseKind


def _normalize(text: str) -> str:
    collapsed = " ".join(text.strip().split())
    return collapsed.strip(_EDGE).strip().casefold()


def _table() -> dict[str, ApprovalPhraseKind]:
    groups: tuple[tuple[ApprovalPhraseKind, tuple[str, ...]], ...] = (
        ("once", _ONCE),
        ("tool", _TOOL),
        ("all", _ALL),
        ("reject", _REJECT),
        ("reset", _RESET),
    )
    out: dict[str, ApprovalPhraseKind] = {}
    for kind, phrases in groups:
        for phrase in phrases:
            out[_normalize(phrase)] = kind
    return out


_PHRASES = _table()


def match_approval_utterance(text: str | None) -> ApprovalUtterance | None:
    """Return a decision when *text* is only an approval phrase."""
    if not text or not text.strip():
        return None
    kind = _PHRASES.get(_normalize(text))
    if kind is None:
        return None
    return ApprovalUtterance(kind=kind)
