"""Malformed checkpoint stamps must not discard or break history messages."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import HumanMessage

from octop.api.routers.chat.serialize import _serialize_history_message
from octop.infra.gateway.process.message_keys import CHECKPOINT_TS_KEY, parse_checkpoint_ts_ms
from octop.infra.history import projection


@pytest.mark.parametrize("raw", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_checkpoint_keeps_projected_messages(
    raw: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(projection, "now_ts", lambda: 123)
    assert parse_checkpoint_ts_ms(raw) is None
    message = HumanMessage(content="keep this", additional_kwargs={CHECKPOINT_TS_KEY: raw})
    item = projection.message_input(message)
    assert item is not None
    assert item.created_at == 123
    assert json.loads(item.message_json)["data"]["content"] == "keep this"
    live = projection.live_message_input(message, now_ms=1_700_000_000_123)
    assert live is not None
    assert live.created_at == 1_700_000_000
    wire = json.loads(live.message_json)
    assert wire["data"]["additional_kwargs"][CHECKPOINT_TS_KEY] == 1_700_000_000_123


@pytest.mark.parametrize("raw", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_checkpoint_uses_history_row_timestamp(raw: float) -> None:
    entry = _serialize_history_message(
        HumanMessage(content="keep this", additional_kwargs={CHECKPOINT_TS_KEY: raw}),
        fallback_created_at=1_700_000_000,
    )
    assert entry is not None
    assert entry["content"] == [{"type": "text", "text": "keep this"}]
    assert entry["timestamp"] == 1_700_000_000_000


def test_positive_integer_does_not_require_float_conversion() -> None:
    timestamp = 10**400
    assert parse_checkpoint_ts_ms(timestamp) == timestamp
