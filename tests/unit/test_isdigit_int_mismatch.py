"""Regression tests: ``isdigit()`` accepts code points ``int()`` rejects.

``str.isdigit()`` is true for 128 non-decimal code points (superscripts, circled
digits, superscript East-Arabic digits). Every ``isdigit()``-then-``int()`` parse
in the codebase therefore raises ``ValueError`` on those inputs instead of
declining them the way the sibling parsers do.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from octop.infra.agents.settings import runtime_limits
from octop.infra.knowledge import gate

# One representative per isdigit-but-not-int family: superscript, circled digit.
NON_DECIMAL_DIGITS = ["²", "①"]


@pytest.mark.parametrize("bad", NON_DECIMAL_DIGITS)
def test_positive_int_declines_non_decimal_digits(bad: str) -> None:
    """``_positive_int`` must return None, not raise, for a non-decimal digit."""
    assert runtime_limits._positive_int(bad) is None


@pytest.mark.parametrize("bad", NON_DECIMAL_DIGITS)
def test_runtime_knobs_survive_non_decimal_digits(bad: str) -> None:
    """The public runtime knobs stay callable and report "unset"."""
    assert runtime_limits.agent_recursion_limit({"max_iters": bad}) is None
    assert runtime_limits.agent_max_input_tokens({"max_input_length": bad}) is None
    assert runtime_limits.agent_model_settings({"max_tokens": bad}) == {}
    assert runtime_limits.resolve_context_max_tokens({"max_input_length": bad}) == 128_000


def test_apply_stream_request_survives_non_decimal_digits() -> None:
    """The stream request builder must not blow up on a poisoned config."""
    req = runtime_limits.apply_agent_runtime_to_stream_request(
        {},
        {"max_iters": "²", "max_input_length": "①", "max_tokens": "²"},
    )
    assert "recursion_limit" not in req


def test_positive_int_still_accepts_plain_decimal_strings() -> None:
    """The existing string contract is unchanged."""
    assert runtime_limits._positive_int("7") == 7
    assert runtime_limits._positive_int(" 42 ") == 42
    assert runtime_limits._positive_int("0") is None
    assert runtime_limits._positive_int("-3") is None
    assert runtime_limits._positive_int("") is None
    assert runtime_limits._positive_int("abc") is None
    assert runtime_limits._positive_int(True) is None


def test_provider_lookup_declines_non_decimal_digits() -> None:
    """``_provider_for_settings`` treats an unparsable id as "no provider"."""
    repo = Mock()
    repo.get.return_value = None
    for bad in NON_DECIMAL_DIGITS:
        assert gate._provider_for_settings(repo, bad) is None
    repo.get.assert_not_called()


def test_capability_payload_survives_non_decimal_provider_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``GET /knowledge-bases/capability`` must not 500 on a poisoned setting."""
    monkeypatch.setattr(gate, "local_embedding_deps_available", lambda: True)
    monkeypatch.setattr(gate, "is_model_downloaded", lambda _model: True)

    values = {
        "knowledge_bases_enabled": "true",
        "knowledge_embedding_model": "BAAI/bge-small-zh-v1.5",
        "knowledge_embedding_provider_id": "²",
    }
    capability = gate.get_capability(values.get, provider_repo=Mock())

    assert capability["provider_id"] == "²"
    assert capability["checks"]["provider_ready"] is False
