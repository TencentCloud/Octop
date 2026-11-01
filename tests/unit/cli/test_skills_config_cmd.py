"""Tests for the interactive ``octop skills config`` toggling."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from octop.cli.main import cli

SKILLS = [
    {"slug": "pdf", "name": "pdf", "enabled": True, "kind": "workspace"},
    {"slug": "pdf extra", "name": "pdf extra", "enabled": False, "kind": "workspace"},
]


def _run(
    monkeypatch: pytest.MonkeyPatch,
    skills: list[dict[str, object]],
    selected: list[str],
    captured: dict[str, object] | None = None,
) -> tuple[object, list[tuple[str, bool]]]:
    calls: list[tuple[str, bool]] = []

    def fake_list(_aid: str) -> list[dict[str, object]]:
        return [dict(s) for s in skills]

    def fake_set(_aid: str, name: str, *, enabled: bool) -> None:
        calls.append((name, enabled))

    def fake_checkbox(
        _message: str, *, choices: list[str], defaults: list[str] = ()
    ) -> list[str]:
        if captured is not None:
            captured["choices"] = list(choices)
            captured["defaults"] = list(defaults)
        return list(selected)

    monkeypatch.setattr("octop.cli.support.skills.list_skills_offline", fake_list)
    monkeypatch.setattr("octop.cli.support.skills.set_skill_enabled", fake_set)
    monkeypatch.setattr("octop.cli.support.prompts.checkbox", fake_checkbox)
    result = CliRunner().invoke(cli, ["skills", "config", "--agent", "ag1"])
    return result, calls


def test_config_prechecks_enabled_skills(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    result, _ = _run(monkeypatch, SKILLS, [], captured)
    assert result.exit_code == 0, result.output
    # The checkbox pre-checks its ``defaults`` against the rendered labels.
    assert captured["defaults"] == ["pdf [\u2713] (workspace)"]


def test_config_toggles_the_selected_skill_by_exact_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, calls = _run(monkeypatch, SKILLS, ["pdf extra [\u2717] (workspace)"])
    assert result.exit_code == 0, result.output
    assert calls == [("pdf", False), ("pdf extra", True)]
