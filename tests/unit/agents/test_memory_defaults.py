"""Unit tests for global memory extraction defaults & expert inheritance (#2963)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from octop_memory import MemoryService

from octop.infra.agents.manager import (
    AgentManager,
    _memory_extract_settings,
    memory_extract_supported_options,
)
from octop.infra.agents.settings.memory_defaults import (
    MAX_EXTRACT_RULE_CHARS,
    GlobalMemoryDefaults,
    load_global_memory_defaults,
    normalize_rule_text,
    resolve_effective_memory_defaults,
    save_global_memory_defaults,
)


class _MemSettingsRepo:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value


def test_global_memory_defaults_roundtrip_and_corrupt_recovery() -> None:
    repo = _MemSettingsRepo()
    assert load_global_memory_defaults(repo) == GlobalMemoryDefaults()

    saved = save_global_memory_defaults(
        repo,
        GlobalMemoryDefaults(
            aux_model="  hai/MiniMax-M2.7 ",
            extract_keep_rules="  Keep durable preferences  ",
            extract_skip_rules="  Skip casual greetings  ",
        ),
    )
    assert saved == GlobalMemoryDefaults(
        aux_model="hai/MiniMax-M2.7",
        extract_keep_rules="Keep durable preferences",
        extract_skip_rules="Skip casual greetings",
    )
    assert load_global_memory_defaults(repo) == saved

    repo.set("memory_global_defaults", "{not-json")
    assert load_global_memory_defaults(repo) == GlobalMemoryDefaults()


def test_normalize_rule_text_strict_vs_lenient() -> None:
    with pytest.raises(ValueError, match="at most"):
        normalize_rule_text("x" * (MAX_EXTRACT_RULE_CHARS + 1), strict=True)
    with pytest.raises(ValueError, match="string"):
        normalize_rule_text(123, strict=True)
    assert len(normalize_rule_text("x" * (MAX_EXTRACT_RULE_CHARS + 50))) == MAX_EXTRACT_RULE_CHARS
    assert normalize_rule_text(None) == ""


def test_resolve_effective_memory_defaults_legacy_and_independent_modes() -> None:
    glob = GlobalMemoryDefaults(
        aux_model="hai/MiniMax-M2.7",
        extract_keep_rules="Global keep",
        extract_skip_rules="Global skip",
    )

    # 1. Brand-new expert (no memory section) inherits both.
    eff_new = resolve_effective_memory_defaults({}, glob)
    assert eff_new.aux_model_mode == "inherit"
    assert eff_new.extract_rules_mode == "inherit"
    assert eff_new.effective_aux_model == "hai/MiniMax-M2.7"
    assert eff_new.effective_keep_rules == "Global keep"
    assert eff_new.effective_skip_rules == "Global skip"

    # 2. Legacy expert with explicit null aux_model still inherits global.
    eff_legacy_auto = resolve_effective_memory_defaults({"aux_model": None}, glob)
    assert eff_legacy_auto.aux_model_mode == "inherit"
    assert eff_legacy_auto.effective_aux_model == "hai/MiniMax-M2.7"

    # 3. Legacy expert with pinned aux_model preserves custom override, while inheriting rules.
    eff_legacy_custom = resolve_effective_memory_defaults({"aux_model": "openai/gpt-4o-mini"}, glob)
    assert eff_legacy_custom.aux_model_mode == "custom"
    assert eff_legacy_custom.aux_model == "openai/gpt-4o-mini"
    assert eff_legacy_custom.effective_aux_model == "openai/gpt-4o-mini"
    assert eff_legacy_custom.extract_rules_mode == "inherit"
    assert eff_legacy_custom.effective_keep_rules == "Global keep"

    # 4. Expert explicitly overriding model to AUTO (follow its own chat model).
    eff_explicit_chat = resolve_effective_memory_defaults(
        {"aux_model_mode": "custom", "aux_model": None},
        glob,
    )
    assert eff_explicit_chat.aux_model_mode == "custom"
    assert eff_explicit_chat.aux_model is None
    assert eff_explicit_chat.effective_aux_model is None

    # 5. Expert overriding only rules while still inheriting model.
    eff_rules_override = resolve_effective_memory_defaults(
        {
            "aux_model_mode": "inherit",
            "extract_rules_mode": "custom",
            "extract_keep_rules": "Domain-specific keep",
            "extract_skip_rules": "",
        },
        glob,
    )
    assert eff_rules_override.effective_aux_model == "hai/MiniMax-M2.7"
    assert eff_rules_override.effective_keep_rules == "Domain-specific keep"
    assert eff_rules_override.effective_skip_rules == ""


def test_memory_extract_settings_applies_global_defaults_to_fresh_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MemoryService, "supports_extraction_rules", True, raising=False)
    glob = GlobalMemoryDefaults(
        aux_model="hai/MiniMax-M2.7",
        extract_keep_rules="Keep stable user prefs",
        extract_skip_rules="Skip weather small talk",
    )
    supported = frozenset(
        {
            "memory_aux_light_model",
            "memory_aux_heavy_model",
            "memory_extract_keep_rules",
            "memory_extract_skip_rules",
        }
    )
    settings = _memory_extract_settings(
        {},
        supported_fields=supported,
        is_ref_usable=lambda ref: ref == "hai/MiniMax-M2.7",
        global_defaults=glob,
    )
    assert settings == {
        "memory_aux_light_model": "hai/MiniMax-M2.7",
        "memory_aux_heavy_model": "hai/MiniMax-M2.7",
        "memory_extract_keep_rules": "Keep stable user prefs",
        "memory_extract_skip_rules": "Skip weather small talk",
    }


def test_memory_extract_settings_drops_extra_body_when_inherited_global_model_is_stale() -> None:
    glob = GlobalMemoryDefaults(aux_model="deleted/model")
    settings = _memory_extract_settings(
        {"memory": {"extract_extra_body": {"reasoning_effort": "low"}}},
        supported_fields=frozenset(
            {
                "memory_aux_light_model",
                "memory_aux_heavy_model",
                "memory_aux_extra_body",
            }
        ),
        is_ref_usable=lambda _ref: False,
        global_defaults=glob,
    )
    assert settings == {}


def test_memory_extract_settings_skips_rules_on_legacy_harness() -> None:
    glob = GlobalMemoryDefaults(
        extract_keep_rules="Keep decisions",
        extract_skip_rules="Skip noise",
    )
    settings = _memory_extract_settings(
        {},
        supported_fields=frozenset({"memory_enabled"}),
        global_defaults=glob,
    )
    assert settings == {}


def test_memory_extract_supported_options_advertises_extract_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.agents import manager as module

    monkeypatch.setattr(
        module,
        "_HARNESS_AGENT_CONFIG_FIELDS",
        frozenset({"memory_extract_keep_rules", "memory_extract_skip_rules"}),
    )
    monkeypatch.delattr(MemoryService, "supports_extraction_rules", raising=False)
    assert "extract_rules" not in memory_extract_supported_options()
    assert (
        _memory_extract_settings(
            {},
            supported_fields=module._HARNESS_AGENT_CONFIG_FIELDS,
            global_defaults=GlobalMemoryDefaults(extract_keep_rules="Keep"),
        )
        == {}
    )
    monkeypatch.setattr(MemoryService, "supports_extraction_rules", True, raising=False)
    assert memory_extract_supported_options() == ["extract_rules"]

    monkeypatch.setattr(
        module,
        "_HARNESS_AGENT_CONFIG_FIELDS",
        frozenset({"memory_extract_keep_rules"}),
    )
    assert memory_extract_supported_options() == []


def _fake_row(agent_id: str, config: dict | None = None, *, enabled: bool = True) -> Any:
    return SimpleNamespace(
        agent_id=agent_id,
        name=agent_id,
        user_id=1,
        default_model=None,
        system_prompt=None,
        enabled=enabled,
        config_json=json.dumps(config or {}),
        last_state="running",
        last_error=None,
    )


@pytest.mark.asyncio
async def test_on_global_memory_defaults_changed_reloads_only_inheriting_agents() -> None:
    rows = [
        _fake_row("fresh-inherit", {}),
        _fake_row("custom-model-only", {"memory": {"aux_model": "prov/custom"}}),
        _fake_row(
            "custom-rules-only",
            {
                "memory": {
                    "aux_model_mode": "inherit",
                    "extract_rules_mode": "custom",
                    "extract_keep_rules": "Only mine",
                }
            },
        ),
        _fake_row("memory-off", {"memory": {"memory_enabled": False}}),
    ]
    mgr = AgentManager.__new__(AgentManager)
    mgr._repos = SimpleNamespace(
        agent_repo=SimpleNamespace(list_all=lambda include_disabled=False: rows),
        settings_repo=_MemSettingsRepo(),
    )
    mgr._harness_manager = SimpleNamespace()
    mgr._reload_agents = AsyncMock()

    # Changing only global aux_model reloads fresh-inherit + custom-rules-only.
    reloaded_model = await mgr.on_global_memory_defaults_changed(
        aux_model_changed=True,
        rules_changed=False,
    )
    assert reloaded_model == ["fresh-inherit", "custom-rules-only"]
    mgr._reload_agents.assert_awaited_once_with(["fresh-inherit", "custom-rules-only"])

    mgr._reload_agents.reset_mock()
    # Changing only global rules reloads fresh-inherit + custom-model-only.
    reloaded_rules = await mgr.on_global_memory_defaults_changed(
        aux_model_changed=False,
        rules_changed=True,
    )
    assert reloaded_rules == ["fresh-inherit", "custom-model-only"]
    mgr._reload_agents.assert_awaited_once_with(["fresh-inherit", "custom-model-only"])


def test_memory_aux_provider_impact_catches_inheriting_and_live_agents() -> None:
    settings_repo = _MemSettingsRepo()
    save_global_memory_defaults(
        settings_repo,
        GlobalMemoryDefaults(aux_model="target-prov/mini"),
    )
    rows = [
        _fake_row("inherits-global", {}),
        _fake_row("custom-other", {"memory": {"aux_model": "other-prov/fast"}}),
        _fake_row("custom-target", {"memory": {"aux_model": "target-prov/big"}}),
        _fake_row("off", {"memory": {"memory_enabled": False}}),
        _fake_row("live-off", {"memory": {"aux_model_mode": "custom"}}),
        _fake_row("live-stale", {"memory": {"aux_model_mode": "custom", "aux_model": None}}),
    ]
    mgr = AgentManager.__new__(AgentManager)
    mgr._repos = SimpleNamespace(settings_repo=settings_repo)
    mgr._harness_manager = SimpleNamespace(
        list_agents=lambda: [
            SimpleNamespace(
                agent_id="off",
                config=SimpleNamespace(
                    memory_enabled=True, memory_aux_light_model="target-prov/old"
                ),
            ),
            SimpleNamespace(
                agent_id="live-off",
                config=SimpleNamespace(
                    memory_enabled=False, memory_aux_light_model="target-prov/old"
                ),
            ),
            SimpleNamespace(
                agent_id="live-stale",
                config=SimpleNamespace(
                    memory_aux_light_model="target-prov/old",
                    memory_aux_heavy_model="target-prov/old",
                ),
            ),
        ]
    )

    impact = mgr._memory_aux_provider_impact_ids(provider_name="target-prov", rows=rows)
    assert impact == {"inherits-global", "custom-target", "live-stale"}


@pytest.mark.asyncio
async def test_affected_includes_stopped_expert_without_attempting_reload() -> None:
    stopped = _fake_row("stopped")
    stopped.last_state = "stopped"
    mgr = AgentManager.__new__(AgentManager)
    mgr._repos = SimpleNamespace(
        agent_repo=SimpleNamespace(list_all=lambda **_: [stopped, _fake_row("running")])
    )
    mgr._reload_agents = AsyncMock()
    mgr._harness_manager = None
    assert await mgr.on_global_memory_defaults_changed(
        aux_model_changed=True, rules_changed=False
    ) == ["stopped", "running"]
    mgr._reload_agents.assert_not_awaited()
    mgr._harness_manager = SimpleNamespace()
    assert await mgr.on_global_memory_defaults_changed(
        aux_model_changed=True, rules_changed=False
    ) == ["stopped", "running"]
    mgr._reload_agents.assert_awaited_once_with(["running"])
