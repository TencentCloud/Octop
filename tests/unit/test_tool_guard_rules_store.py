"""Tests for user-editable tool guard rules store."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.agents.security import ToolGuardRulesStore
from octop.infra.agents.security.tool_guard_rules import TOOL_GUARD_YAML
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def rules_store(tmp_path: Path) -> ToolGuardRulesStore:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return ToolGuardRulesStore(paths=PathLayout(tmp_path), settings=SettingsRepo(db))


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


def test_legacy_file_is_adopted_once(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    settings = SettingsRepo(db)
    first_home = PathLayout(tmp_path / "first")
    first_home.tool_guard_rules_file.parent.mkdir(parents=True)
    first_home.tool_guard_rules_file.write_text("rules: from-first\n", encoding="utf-8")
    first = ToolGuardRulesStore(paths=first_home, settings=settings)
    first.ensure_seeded()

    second_home = PathLayout(tmp_path / "second")
    second_home.tool_guard_rules_file.parent.mkdir(parents=True)
    second_home.tool_guard_rules_file.write_text("rules: from-second\n", encoding="utf-8")
    second = ToolGuardRulesStore(paths=second_home, settings=settings)
    second.ensure_seeded()

    assert second.read_text() == "rules: from-first\n"
    assert second.rules_file.read_text(encoding="utf-8") == "rules: from-first\n"
    assert settings.get(TOOL_GUARD_YAML) == "rules: from-first\n"


def test_second_store_reads_settings_not_a_stale_file(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    settings = SettingsRepo(db)
    first = ToolGuardRulesStore(paths=PathLayout(tmp_path), settings=settings)
    first.ensure_seeded()
    saved = first.read_text()
    first.rules_file.write_text("stale: true\n", encoding="utf-8")
    second = ToolGuardRulesStore(paths=PathLayout(tmp_path / "other"), settings=settings)
    second.ensure_seeded()
    assert second.read_text() == saved
    assert settings.get(TOOL_GUARD_YAML) == saved
    assert second.rules_file.read_text(encoding="utf-8") == saved
