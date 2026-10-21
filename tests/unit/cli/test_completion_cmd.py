"""Tests for `octop completion`."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.main import cli


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_completion_show_emits_script(shell: str) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["completion", "show", "--shell", shell])
    assert result.exit_code == 0
    assert "_AGENTBUDDY_COMPLETE" in result.output


def test_completion_install_appends_eval_line_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rc = tmp_path / ".bashrc"
    rc.write_text("# existing\n")
    monkeypatch.setenv("HOME", str(tmp_path))

    runner = CliRunner()
    r1 = runner.invoke(cli, ["completion", "install", "--shell", "bash", "--rc-file", str(rc)])
    assert r1.exit_code == 0, r1.output
    contents = rc.read_text()
    assert "_AGENTBUDDY_COMPLETE" in contents
    line_count_first = contents.count("_AGENTBUDDY_COMPLETE")

    r2 = runner.invoke(cli, ["completion", "install", "--shell", "bash", "--rc-file", str(rc)])
    assert r2.exit_code == 0
    assert rc.read_text().count("_AGENTBUDDY_COMPLETE") == line_count_first


def test_completion_in_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "completion" in result.output
