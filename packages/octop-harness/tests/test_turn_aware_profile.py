"""Tests for turn-aware summarization profile thresholds."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from deepagents.middleware.summarization import compute_summarization_defaults
from langchain.agents.middleware.summarization import SummarizationMiddleware
from langchain_core.messages import HumanMessage

from octop_harness.middleware.turn_aware_profile import (
    TurnAwareProfile,
    install_turn_aware_profile,
)
from octop_harness.middleware.turn_model import resolve_turn_model_ref


def _model_with_profile(max_input_tokens: int) -> MagicMock:
    m = MagicMock(name=f"model-{max_input_tokens}")
    m.profile = {"max_input_tokens": max_input_tokens}
    return m


@pytest.fixture
def factory() -> MagicMock:
    models = {
        "p/minimax": _model_with_profile(1_000_000),
        "p/kimi": _model_with_profile(131_072),
        "p/vision": _model_with_profile(200_000),
    }
    factory = MagicMock()
    factory.get_chat_model.side_effect = lambda ref: models[ref]
    return factory


def test_resolve_turn_model_ref_uses_configurable_override() -> None:
    assert (
        resolve_turn_model_ref(
            pick_default_ref=lambda: "p/minimax",
            configurable={"model": "p/kimi"},
        )
        == "p/kimi"
    )


def test_resolve_turn_model_ref_falls_back_to_default() -> None:
    assert resolve_turn_model_ref(pick_default_ref=lambda: "p/minimax") == "p/minimax"


def test_resolve_turn_model_ref_multimodal() -> None:
    msg = HumanMessage(content=[{"type": "text", "text": "see"}, {"type": "image_url", "image_url": {"url": "x"}}])
    assert (
        resolve_turn_model_ref(
            pick_default_ref=lambda: "p/minimax",
            messages=[msg],
            pick_multimodal_ref=lambda: "p/vision",
        )
        == "p/vision"
    )


def test_profile_follows_turn_model(factory: MagicMock) -> None:
    seed = _model_with_profile(1_000_000)
    install_turn_aware_profile(
        seed,
        factory=factory,
        pick_default_ref=lambda: "p/minimax",
    )
    assert isinstance(seed.profile, TurnAwareProfile)
    assert isinstance(seed.profile, dict)

    with patch(
        "octop_harness.middleware.turn_aware_profile._configurable_from_runtime",
        return_value={},
    ):
        assert seed.profile.get("max_input_tokens") == 1_000_000

    with patch(
        "octop_harness.middleware.turn_aware_profile._configurable_from_runtime",
        return_value={"model": "p/kimi"},
    ):
        assert seed.profile["max_input_tokens"] == 131_072
        assert seed.profile.get("max_input_tokens") == 131_072
        assert "max_input_tokens" in seed.profile


def test_compute_defaults_still_picks_fraction_with_aware_profile(
    factory: MagicMock,
) -> None:
    seed = _model_with_profile(1_000_000)
    install_turn_aware_profile(
        seed,
        factory=factory,
        pick_default_ref=lambda: "p/minimax",
    )
    defaults = compute_summarization_defaults(seed)
    assert defaults["trigger"] == ("fraction", 0.85)
    assert defaults["keep"] == ("fraction", 0.10)


def test_should_summarize_respects_turn_window(factory: MagicMock) -> None:
    seed = _model_with_profile(1_000_000)
    install_turn_aware_profile(
        seed,
        factory=factory,
        pick_default_ref=lambda: "p/minimax",
    )
    defaults = compute_summarization_defaults(seed)
    mw = SummarizationMiddleware(
        model=seed,
        trigger=defaults["trigger"],
        keep=defaults["keep"],
    )
    messages: list[Any] = [HumanMessage(content="x")]
    tokens = 120_000

    with patch(
        "octop_harness.middleware.turn_aware_profile._configurable_from_runtime",
        return_value={"model": "p/kimi"},
    ):
        assert mw._should_summarize(messages, tokens) is True

    with patch(
        "octop_harness.middleware.turn_aware_profile._configurable_from_runtime",
        return_value={"model": "p/minimax"},
    ):
        assert mw._should_summarize(messages, tokens) is False
