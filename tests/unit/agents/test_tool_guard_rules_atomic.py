"""The tool guard rules file must never be left half written."""

from __future__ import annotations

import os

import pytest

from octop.infra.agents.security.tool_guard_rules import ToolGuardRulesStore


class _Paths:
    def __init__(self, root):
        self._root = root

    @property
    def tool_guard_rules_dir(self):
        return self._root

    @property
    def tool_guard_rules_file(self):
        return self._root / "rules.yaml"


def test_a_failed_save_keeps_the_previous_rules(tmp_path, monkeypatch):
    store = ToolGuardRulesStore(paths=_Paths(tmp_path))
    store.ensure_seeded()
    before = store.read_text()

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        store.save_text(before)

    # A truncating write would leave a partial YAML that every later read parses,
    # and ensure_seeded only restores the file when it is absent.
    assert store.rules_file.read_text(encoding="utf-8") == before
    assert list(tmp_path.glob("*.tmp")) == []


def test_seeding_and_saving_still_work(tmp_path):
    store = ToolGuardRulesStore(paths=_Paths(tmp_path))

    store.ensure_seeded()
    text = store.read_text()
    count, errors = store.save_text(text)

    assert errors == []
    assert count > 0
    assert store.rules_file.read_text(encoding="utf-8") == text
