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


# Two rules the user saved earlier; the file is seeded directly so these tests do
# not depend on the bundled rules that ship with octop_harness.
_CUSTOM_RULES = """\
- id: CUSTOM_RULE_A
  tools: [bash]
  params: [command]
  category: command_injection
  severity: HIGH
  patterns:
    - "\\\\balicecmd\\\\b"
  description: "A"
  remediation: "no"
- id: CUSTOM_RULE_B
  tools: [bash]
  params: [command]
  category: command_injection
  severity: HIGH
  patterns:
    - "\\\\bbobcmd\\\\b"
  description: "B"
  remediation: "no"
"""

_INCOMING = """\
- id: NEW_RULE
  tools: [bash]
  params: [command]
  category: command_injection
  severity: HIGH
  patterns:
    - "\\\\bcarolcmd\\\\b"
  description: "C"
  remediation: "no"
"""


def _seeded_store(tmp_path: Path) -> ToolGuardRulesStore:
    """A store whose rules file already holds known-good custom rules."""
    store = ToolGuardRulesStore(paths=PathLayout(tmp_path))
    store.rules_dir.mkdir(parents=True, exist_ok=True)
    store.rules_file.write_text(_CUSTOM_RULES, encoding="utf-8")
    return store


def _stub_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the store a real ``validate_rules_yaml`` return value.

    ``validate_rules_yaml`` comes from the internal ``octop_harness`` package,
    which is not installable here, so the local autostub hands back a
    non-tuple. The count is irrelevant to these tests — what matters is which
    text ends up on disk.
    """
    monkeypatch.setattr(
        "octop.infra.agents.security.tool_guard_rules.validate_rules_yaml",
        lambda content: ([{"id": "x"}], []),
    )


def _fail_write_text_after(prefix_len: int):
    """Patch ``Path.write_text`` so it writes a prefix then fails like a full disk."""
    real = Path.write_text

    def _failing(self: Path, data: str, **kwargs: object) -> int:
        real(self, data[:prefix_len], **kwargs)
        raise OSError(28, "No space left on device")

    return real, _failing


def test_failed_save_keeps_previous_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A save that dies mid-write must not truncate the stored rules.

    ``save_text`` validates the submitted text and then rewrites the file in
    place, so a full disk or a killed process leaves a partial YAML document.
    Partial is the dangerous case here: a truncated rule list still parses, so
    the agent runtime loads it and the dangerous-command guard quietly matches
    fewer rules than the user configured.
    """
    _stub_validator(monkeypatch)
    store = _seeded_store(tmp_path)

    real, failing = _fail_write_text_after(20)
    Path.write_text = failing  # type: ignore[method-assign]
    try:
        with pytest.raises(OSError):
            store.save_text(_INCOMING)
    finally:
        Path.write_text = real  # type: ignore[method-assign]

    assert store.rules_file.read_text(encoding="utf-8") == _CUSTOM_RULES, (
        "the previously saved rules were destroyed by a failed save"
    )


def test_failed_save_leaves_no_temp_debris(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The staged file is removed when the write fails."""
    _stub_validator(monkeypatch)
    store = _seeded_store(tmp_path)

    def _failing(self: Path, data: str, **kwargs: object) -> int:
        raise OSError(28, "No space left on device")

    real = Path.write_text
    Path.write_text = _failing  # type: ignore[method-assign]
    try:
        with pytest.raises(OSError):
            store.save_text(_INCOMING)
    finally:
        Path.write_text = real  # type: ignore[method-assign]

    names = sorted(p.name for p in store.rules_dir.iterdir())
    assert names == [store.rules_file.name], f"temp debris left behind: {names}"


def test_reset_to_bundled_keeps_previous_rules_when_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``reset_to_bundled`` rewrites in place as well, so it needs the same guard."""
    store = _seeded_store(tmp_path)
    monkeypatch.setattr(
        "octop.infra.agents.security.tool_guard_rules.read_bundled_rules_yaml",
        lambda: _CUSTOM_RULES,
    )

    def _failing(self: Path, data: str, **kwargs: object) -> int:
        raise OSError(28, "No space left on device")

    real = Path.write_text
    Path.write_text = _failing  # type: ignore[method-assign]
    try:
        with pytest.raises(OSError):
            store.reset_to_bundled()
    finally:
        Path.write_text = real  # type: ignore[method-assign]

    assert store.rules_file.read_text(encoding="utf-8") == _CUSTOM_RULES, (
        "custom rules were destroyed by a failed reset"
    )


def test_successful_save_still_replaces_the_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The happy path is unchanged: a valid save replaces the file wholesale."""
    _stub_validator(monkeypatch)
    store = _seeded_store(tmp_path)
    _count, errors = store.save_text(_INCOMING)
    assert errors == []
    assert store.rules_file.read_text(encoding="utf-8") == _INCOMING
