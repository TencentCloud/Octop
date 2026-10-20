"""Tests for configurable model-settings middleware."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from langchain.agents.middleware import ModelRequest

from octop_harness.middleware.model_settings import apply_configurable_model_settings


@dataclass
class _FakeModel:
    profile: dict[str, Any] | None = None


def test_apply_configurable_model_settings_merges_generation_knobs() -> None:
    request = ModelRequest(
        model=_FakeModel(),
        messages=[],
        model_settings={"temperature": 1.0},
    )
    runtime = {"configurable": {"model_settings": {"temperature": 0.3, "top_p": 0.8, "max_tokens": 512}}}
    with patch(
        "octop_harness.middleware.model_settings.runtime_config",
        return_value=runtime,
    ):
        updated = apply_configurable_model_settings(request)
    assert updated.model_settings == {
        "temperature": 0.3,
        "top_p": 0.8,
        "max_tokens": 512,
    }


def test_apply_configurable_model_settings_sets_context_cap_on_model_profile() -> None:
    model = _FakeModel(profile={"max_input_tokens": 128_000})
    request = ModelRequest(model=model, messages=[], model_settings={})
    runtime = {"configurable": {"max_input_tokens": 64_000}}
    with patch(
        "octop_harness.middleware.model_settings.runtime_config",
        return_value=runtime,
    ):
        updated = apply_configurable_model_settings(request)
    assert updated.model is model
    assert model.profile is not None
    assert model.profile["max_input_tokens"] == 64_000


def test_apply_configurable_model_settings_reserves_requested_output() -> None:
    model = _FakeModel(profile={"max_input_tokens": 1_000_000, "context_window": 1_000_000})
    request = ModelRequest(model=model, messages=[], model_settings={})
    runtime = {"configurable": {"model_settings": {"max_tokens": 64_000}}}
    with patch(
        "octop_harness.middleware.model_settings.runtime_config",
        return_value=runtime,
    ):
        apply_configurable_model_settings(request)
    assert model.profile is not None
    assert model.profile["max_input_tokens"] == 936_000
