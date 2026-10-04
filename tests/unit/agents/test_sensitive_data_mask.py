"""SensitiveDataMaskMiddleware: mainland phone / ID card detection and masking."""

from __future__ import annotations

from typing import Any

import pytest
from langchain.agents.middleware import PIIDetectionError
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from octop.infra.agents.middleware.sensitive_data import (
    SensitiveDataMaskMiddleware,
    detect_sensitive_data,
)

# Realistic but syntactically valid samples (not real people).
_PHONE = "13812345678"
_PHONE_MASKED = "138****5678"
_ID = "11010119900307885X"
_ID_MASKED = "110101********885X"


def _spans(text: str) -> list[tuple[str, str]]:
    return [(m["type"], m["value"]) for m in detect_sensitive_data(text)]


# ---------------------------------------------------------------- detector


def test_detects_phone_in_text() -> None:
    assert _spans(f"请联系 {_PHONE} 谢谢") == [("cn_mobile_phone", _PHONE)]


def test_detects_id_card_in_text() -> None:
    assert _spans(f"身份证号：{_ID}。") == [("cn_id_card", _ID)]


def test_detects_id_card_lowercase_x() -> None:
    assert _spans("11010119900307885x") == [("cn_id_card", "11010119900307885x")]


def test_detects_both_in_one_text() -> None:
    spans = _spans(f"手机 {_PHONE}，证件 {_ID}")
    assert spans == [("cn_mobile_phone", _PHONE), ("cn_id_card", _ID)]


def test_rejects_phone_with_wrong_second_digit() -> None:
    # 11 digits but second digit is 2 -> not a mainland mobile number.
    assert _spans("12345678901") == []


def test_rejects_phone_with_wrong_length_prefix() -> None:
    # Starts with 0 / 2 -> not a mobile number.
    assert _spans("23456789012") == []


def test_rejects_phone_inside_longer_digit_run() -> None:
    # 12-digit run: the trailing 11 digits must not match (digit lookahead),
    # and the leading 11 must not either when followed by a digit.
    assert _spans("9138123456781") == []


def test_rejects_phone_adjacent_to_digits() -> None:
    assert _spans("8613812345678") == []


def test_rejects_17_digit_run_as_id_card() -> None:
    assert _spans("12345678901234567") == []


def test_rejects_id_card_inside_longer_digit_run() -> None:
    # 20-digit run: no 18-char window may match in the middle.
    assert _spans("9" + "110101199003078851" + "2") == []


def test_rejects_id_card_with_trailing_digit() -> None:
    # 18 digits followed by another digit -> the run is 19 long, no match.
    assert _spans("1101011990030788512") == []


# ---------------------------------------------------------------- masking


def _mw(**kwargs: Any) -> SensitiveDataMaskMiddleware:
    return SensitiveDataMaskMiddleware(**kwargs)


def test_mask_phone_keeps_head3_tail4() -> None:
    mw = _mw(strategy="mask", apply_to_input=True)
    state: dict[str, Any] = {"messages": [HumanMessage(content=f"电话 {_PHONE}")]}
    updated = mw.before_model(state, None)
    assert updated is not None
    assert updated["messages"][0].content == f"电话 {_PHONE_MASKED}"


def test_mask_id_card_keeps_head6_tail4() -> None:
    mw = _mw(strategy="mask", apply_to_input=True)
    state: dict[str, Any] = {"messages": [HumanMessage(content=f"证件 {_ID}")]}
    updated = mw.before_model(state, None)
    assert updated["messages"][0].content == f"证件 {_ID_MASKED}"


def test_mask_preserves_star_count() -> None:
    # 4 stars for phone (11-7), 8 stars for ID (18-10).
    assert _PHONE_MASKED.count("*") == 4
    assert _ID_MASKED.count("*") == 8


# ---------------------------------------------------------------- surfaces


def test_input_surface_disabled_is_noop() -> None:
    mw = _mw(strategy="mask", apply_to_input=False)
    state: dict[str, Any] = {"messages": [HumanMessage(content=f"电话 {_PHONE}")]}
    assert mw.before_model(state, None) is None


def test_output_surface_masks_ai_message() -> None:
    mw = _mw(strategy="mask", apply_to_output=True)
    state: dict[str, Any] = {"messages": [AIMessage(content=f"他的号码是 {_PHONE}")]}
    updated = mw.after_model(state, None)
    assert updated is not None
    assert updated["messages"][0].content == f"他的号码是 {_PHONE_MASKED}"


def test_tool_result_surface_masks_tool_message() -> None:
    mw = _mw(strategy="mask", apply_to_tool_results=True, apply_to_input=False)
    state: dict[str, Any] = {
        "messages": [
            HumanMessage(content="查一下"),
            AIMessage(content="", tool_calls=[]),
            ToolMessage(content=f"联系人: {_PHONE} / {_ID}", tool_call_id="tc1"),
        ]
    }
    updated = mw.before_model(state, None)
    assert updated is not None
    assert updated["messages"][2].content == f"联系人: {_PHONE_MASKED} / {_ID_MASKED}"


def test_clean_text_returns_none() -> None:
    mw = _mw(strategy="mask", apply_to_input=True, apply_to_output=True)
    state: dict[str, Any] = {"messages": [HumanMessage(content="没有任何敏感信息 2024-01-01")]}
    assert mw.before_model(state, None) is None
    assert mw.after_model({"messages": [AIMessage(content="普通回复")]}, None) is None


def test_block_list_content_only_masks_text_blocks() -> None:
    mw = _mw(strategy="mask", apply_to_output=True)
    content: list[dict[str, Any]] = [
        {"type": "text", "text": f"号码 {_PHONE}"},
        {"type": "image_url", "image_url": {"url": "http://example.invalid/a.png"}},
    ]
    state: dict[str, Any] = {"messages": [AIMessage(content=content)]}
    updated = mw.after_model(state, None)
    assert updated is not None
    blocks = updated["messages"][0].content
    assert blocks[0]["text"] == f"号码 {_PHONE_MASKED}"
    assert blocks[1] == content[1]


# ---------------------------------------------------------------- strategies


def test_redact_strategy_placeholder() -> None:
    mw = _mw(strategy="redact", apply_to_input=True)
    state: dict[str, Any] = {"messages": [HumanMessage(content=f"{_PHONE}")]}
    updated = mw.before_model(state, None)
    assert updated["messages"][0].content == "[REDACTED_CN_MOBILE_PHONE]"


def test_hash_strategy_is_deterministic() -> None:
    mw = _mw(strategy="hash", apply_to_input=True)
    state: dict[str, Any] = {"messages": [HumanMessage(content=f"{_PHONE}")]}
    first = mw.before_model(state, None)
    second = mw.before_model(state, None)
    assert first is not None and second is not None
    assert first["messages"][0].content == second["messages"][0].content
    assert first["messages"][0].content.startswith("<cn_mobile_phone_hash:")


def test_block_strategy_raises() -> None:
    mw = _mw(strategy="block", apply_to_input=True)
    state: dict[str, Any] = {"messages": [HumanMessage(content=f"{_PHONE}")]}
    with pytest.raises(PIIDetectionError):
        mw.before_model(state, None)
