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


def test_completion_in_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "completion" in result.output


def test_completion_install_tolerates_non_utf8_rc_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rc file the default encoding rejects must not abort install.

    ``read_text()`` used the platform default encoding (UTF-8 on Linux, ``cp936``
    on a Chinese Windows) while the appended block is always UTF-8. A rc file
    saved in a legacy encoding therefore raised ``UnicodeDecodeError`` before
    this fix; the idempotence check only needs the ASCII marker, so foreign
    bytes should be replaced instead of aborting the install.
    """
    rc = tmp_path / ".bashrc"
    rc.write_bytes("# 配置文件\n".encode("gbk"))
    monkeypatch.setenv("HOME", str(tmp_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["completion", "install", "--shell", "bash", "--rc-file", str(rc)])
    assert result.exit_code == 0, result.output
    assert "_OCTOP_COMPLETE" in rc.read_text(encoding="utf-8", errors="replace")
