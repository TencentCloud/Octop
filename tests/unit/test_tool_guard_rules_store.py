"""Tests for user-editable tool guard rules store."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.agents.security import ToolGuardRulesStore
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def rules_store(tmp_path: Path) -> ToolGuardRulesStore:
    return ToolGuardRulesStore(paths=PathLayout(tmp_path))


def test_ensure_seeded_creates_yaml(rules_store: ToolGuardRulesStore) -> None:
    rules_store.ensure_seeded()
    assert rules_store.rules_file.is_file()
    content = rules_store.read_text()
    assert "TOOL_CMD_" in content


def test_save_rejects_invalid_yaml(rules_store: ToolGuardRulesStore) -> None:
    rules_store.ensure_seeded()
    count, errors = rules_store.save_text("not: [valid")
    assert count == 0
    assert errors


def test_save_valid_rule_and_reload_catalog(rules_store: ToolGuardRulesStore) -> None:
    rules_store.ensure_seeded()
    yaml_text = """\
- id: CUSTOM_TEST_RULE
  tools: [bash]
  params: [command]
  category: command_injection
  severity: HIGH
  patterns:
    - "\\\\bevilcmd\\\\b"
  description: "Test custom rule"
  remediation: "Do not run evilcmd"
"""
    count, errors = rules_store.save_text(yaml_text)
    assert errors == []
    assert count == 1
    catalog = rules_store.list_catalog()
    assert any(item["id"] == "CUSTOM_TEST_RULE" for item in catalog)


def test_failed_save_keeps_previous_rules(
    rules_store: ToolGuardRulesStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules_store.ensure_seeded()
    original = rules_store.read_text()

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated failure during swap")

    monkeypatch.setattr("os.replace", _boom)
    yaml_text = """\
- id: REPLACEMENT_RULE
  tools: [bash]
  params: [command]
  category: command_injection
  severity: HIGH
  patterns:
    - "\\\\bevilcmd\\\\b"
"""
    with pytest.raises(OSError, match="simulated failure during swap"):
        rules_store.save_text(yaml_text)

    assert rules_store.rules_file.read_text(encoding="utf-8") == original
    assert [entry.name for entry in rules_store.rules_dir.iterdir()] == [
        rules_store.rules_file.name
    ]
