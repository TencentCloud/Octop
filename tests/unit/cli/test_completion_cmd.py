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
    assert "_OCTOP_COMPLETE" in result.output


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
    assert "_OCTOP_COMPLETE" in contents
    line_count_first = contents.count("_OCTOP_COMPLETE")

    r2 = runner.invoke(cli, ["completion", "install", "--shell", "bash", "--rc-file", str(rc)])
    assert r2.exit_code == 0
    assert rc.read_text().count("_OCTOP_COMPLETE") == line_count_first


def test_completion_install_survives_non_ascii_utf8_rc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Chinese user's ``~/.bashrc`` carries UTF-8 comments and aliases.

    The snippet is appended with ``encoding="utf-8"``, but the duplicate check used
    to read the file back with the platform codec — on a GBK/cp936 Windows session
    that raised ``UnicodeDecodeError`` and ``octop completion install`` exited 1
    without writing anything.
    """
    rc = tmp_path / ".bashrc"
    rc.write_text("# 中文备注：自定义补全 🙂\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["completion", "install", "--shell", "bash", "--rc-file", str(rc)])
    assert result.exit_code == 0, result.output
    assert rc.read_text(encoding="utf-8").count("_OCTOP_COMPLETE") == 1


def test_completion_install_detects_marker_in_non_utf8_rc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An rc file saved as ANSI/GBK is still a rc file: the snippet is already there,
    so install must report "already installed" instead of decoding or duplicating it."""
    rc = tmp_path / ".bashrc"
    rc.write_bytes(
        "# 中文备注\nalias gg='git status'\neval \"$(_OCTOP_COMPLETE=bash_source octop)\"\n".encode(
            "gbk"
        )
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    size_before = rc.stat().st_size

    runner = CliRunner()
    result = runner.invoke(cli, ["completion", "install", "--shell", "bash", "--rc-file", str(rc)])
    assert result.exit_code == 0, result.output
    assert "already installed" in result.output
    assert rc.stat().st_size == size_before


def test_completion_in_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "completion" in result.output
