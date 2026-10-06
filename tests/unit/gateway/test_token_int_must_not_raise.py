"""_token_int promises that malformed values must not raise."""

from __future__ import annotations

import json

import pytest

from octop.infra.gateway.process.usage_record import _token_int


@pytest.mark.parametrize(
    "value",
    [
        float("inf"),
        float("-inf"),
        float("nan"),
        "not a number",
        None,
        True,
        {"nested": 1},
        [1],
        -5,
    ],
)
def test_malformed_values_never_raise(value):
    assert _token_int(value) == 0


def test_json_infinity_is_accepted_by_the_stdlib_and_handled():
    # Python's json.loads accepts Infinity/NaN by default, so a provider response
    # can legitimately hand this function a float("inf").
    payload = json.loads('{"input_tokens": Infinity}')

    assert _token_int(payload["input_tokens"]) == 0


def test_valid_counts_still_parse():
    assert _token_int("12") == 12
    assert _token_int(12.0) == 12
    assert _token_int(0) == 0
