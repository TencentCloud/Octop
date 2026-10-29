"""Tests for `octop clean`."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.main import cli


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / ".octop"))
    for key in list(os.environ):
        if key.startswith("OCTOP_DATABASE_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_clean_default_removes_only_cli_state(fake_home: Path) -> None:
    state = fake_home / ".octop" / "cli_state.json"
    state.parent.mkdir(parents=True)
    state.write_text("{}")
    db = fake_home / ".octop" / "octop.db"
    db.write_text("DB-CONTENT")

    runner = CliRunner()
    r = runner.invoke(cli, ["clean", "--yes"])
    assert r.exit_code == 0
    assert not state.exists()
    # default mode preserves server data
    assert db.exists()


def test_clean_all_requires_confirmation(fake_home: Path) -> None:
    db = fake_home / ".octop" / "octop.db"
    db.parent.mkdir(parents=True)
    db.write_text("DB-CONTENT")

    runner = CliRunner()
    r = runner.invoke(cli, ["clean", "--all", "--yes"])
    assert r.exit_code == 0
    assert not db.exists()


def test_clean_dry_run_lists_targets(fake_home: Path) -> None:
    state = fake_home / ".octop" / "cli_state.json"
    state.parent.mkdir(parents=True)
    state.write_text("{}")

    runner = CliRunner()
    r = runner.invoke(cli, ["clean", "--dry-run"])
    assert r.exit_code == 0
    assert "cli_state.json" in r.output
    assert state.exists()  # untouched
