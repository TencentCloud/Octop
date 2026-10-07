"""Tests for `octop completion`."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

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


def _install(rc: Path) -> Result:
    args = ["completion", "install", "--shell", "bash", "--rc-file", str(rc)]
    return CliRunner().invoke(cli, args)


def test_install_reads_utf8_rc_on_a_gbk_session(tmp_path: Path) -> None:
    """The idempotence check must not decode the file, which the write side saves as UTF-8."""
    rc = tmp_path / ".bashrc"
    original = "# 中文备注：自定义补全 🙂\nalias ll='ls -al'\n".encode()
    rc.write_bytes(original)

    result = _install(rc)
    assert result.exit_code == 0, result.output
    assert rc.read_bytes().startswith(original)
    assert rc.read_bytes().count(b"_OCTOP_COMPLETE") == 1


def test_install_detects_the_marker_in_a_gbk_rc(tmp_path: Path) -> None:
    """A GBK-saved rc that already carries the line is left byte-for-byte alone."""
    rc = tmp_path / ".bashrc"
    body = '# 中文备注\n_eval "$(_OCTOP_COMPLETE=bash_complete)"\n'
    rc.write_bytes(body.encode("gbk"))

    result = _install(rc)
    assert result.exit_code == 0, result.output
    assert "already installed" in result.output
    assert rc.read_bytes() == body.encode("gbk")
