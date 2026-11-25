"""Per-expert compaction settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from octop.api.common.agent_runtime import AgentCompactionSettings
from octop.infra.agents.settings.compaction import (
    apply_compaction_update,
    compaction_for_api,
    harness_summarization_kwargs,
    normalize_compaction,
)

_SUPPORTED = frozenset(
    {
        "summarization_enabled",
        "summarization_trigger",
        "summarization_keep",
        "summarization_trim_tokens",
    }
)


def test_normalize_drops_defaults_and_keeps_overrides() -> None:
    assert normalize_compaction(None) is None
    assert normalize_compaction({"enabled": True}) is None
    assert normalize_compaction({"enabled": False}) == {"enabled": False}
    assert normalize_compaction(
        {
            "enabled": True,
            "trigger_fraction": 0.7,
            "keep_fraction": 0.2,
            "trim_tokens": 4000,
        }
    ) == {
        "trigger_fraction": 0.7,
        "keep_fraction": 0.2,
        "trim_tokens": 4000,
    }


def test_normalize_drops_keep_that_is_not_below_the_trigger() -> None:
    assert normalize_compaction({"trigger_fraction": 0.5, "keep_fraction": 0.5}) == {
        "trigger_fraction": 0.5
    }
    assert normalize_compaction({"keep_fraction": 0.9}) is None


def test_apply_compaction_update_clears_with_null() -> None:
    cfg = {"compaction": {"trigger_fraction": 0.7}, "backend": {"type": "state"}}
    assert apply_compaction_update(cfg, None) == {"backend": {"type": "state"}}
    assert cfg["compaction"]["trigger_fraction"] == 0.7


def test_harness_kwargs_follow_the_installed_fields() -> None:
    cfg = {"compaction": {"enabled": False, "trigger_fraction": 0.6, "trim_tokens": 2000}}
    assert harness_summarization_kwargs(cfg, supported_fields=frozenset()) == {}
    assert harness_summarization_kwargs(cfg, supported_fields=_SUPPORTED) == {
        "summarization_enabled": False
    }
    active = {"compaction": {"trigger_fraction": 0.6, "keep_fraction": 0.15, "trim_tokens": 2000}}
    assert harness_summarization_kwargs(active, supported_fields=_SUPPORTED) == {
        "summarization_trigger": ("fraction", 0.6),
        "summarization_keep": ("fraction", 0.15),
        "summarization_trim_tokens": 2000,
    }
    assert compaction_for_api({}) is None


def test_api_model_rejects_keep_at_or_above_the_trigger() -> None:
    AgentCompactionSettings(trigger_fraction=0.7, keep_fraction=0.2, trim_tokens=4000)
    with pytest.raises(ValidationError):
        AgentCompactionSettings(keep_fraction=0.85)
    with pytest.raises(ValidationError):
        AgentCompactionSettings(trigger_fraction=0.4, keep_fraction=0.4)
    with pytest.raises(ValidationError):
        AgentCompactionSettings(trim_tokens=999)
