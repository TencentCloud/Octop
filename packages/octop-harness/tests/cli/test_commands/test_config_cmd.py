"""Tests for harness config command."""

import json
from pathlib import Path

from click.testing import CliRunner

from octop_harness.cli.main import cli


def test_config_list(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "list"])
    assert result.exit_code == 0
    assert "theme" in result.output


def test_config_set_and_get(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    runner = CliRunner()

    result = runner.invoke(cli, ["config", "set", "theme", "light"])
    assert result.exit_code == 0
    assert "Set" in result.output

    config_file = tmp_path / ".octop-harness" / "config.json"
    assert config_file.exists()
    data = json.loads(config_file.read_text())
    assert data["cli"]["theme"] == "light"
