"""Tests for the harness capture-hook arity handling in GlobalProcessor."""

from __future__ import annotations

from typing import Any

import pytest

from octop.infra.gateway.process.processor import GlobalProcessor


@pytest.mark.parametrize(
    ("hook", "expected"),
    [
        (lambda: "scopeless", "scopeless"),
        (lambda thread_id: f"positional:{thread_id}", "positional:t1"),
        (lambda *, thread_id: f"keyword:{thread_id}", "keyword:t1"),
        (lambda *args: f"varargs:{args[0]}", "varargs:t1"),
    ],
)
def test_call_capture_api_matches_hook_arity(hook: Any, expected: str) -> None:
    assert GlobalProcessor._call_capture_api(None, hook, "t1") == expected  # type: ignore[arg-type]
