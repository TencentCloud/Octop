"""Tests for `octop completion`."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.commands.completion import _rc_has_marker
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


def test_rc_has_marker_matches_marker_in_either_encoding(tmp_path: Path) -> None:
    utf8_rc = tmp_path / "utf8"
    utf8_rc.write_bytes("# 中文备注\n_OCTOP_COMPLETE\n".encode())
    gbk_rc = tmp_path / "gbk"
    gbk_rc.write_bytes("# 中文备注\n_OCTOP_COMPLETE\n".encode("gbk"))
    assert _rc_has_marker(utf8_rc)
    assert _rc_has_marker(gbk_rc)

    plain = tmp_path / "plain"
    plain.write_bytes("# 中文备注\n".encode())
    assert not _rc_has_marker(plain)
    assert not _rc_has_marker(tmp_path / "missing")


def test_completion_install_appends_to_rc_saved_as_gbk(tmp_path: Path) -> None:
    # GBK bytes are undecodable as UTF-8 (and vice versa): the command must not
    # decode the file at all, so this fails on every platform before the fix.
    rc = tmp_path / ".bashrc"
    rc.write_bytes("# 中文备注\nalias ll='ls -al'\n".encode("gbk"))

    runner = CliRunner()
    r1 = runner.invoke(cli, ["completion", "install", "--shell", "bash", "--rc-file", str(rc)])
    assert r1.exit_code == 0, r1.output
    assert b"_OCTOP_COMPLETE" in rc.read_bytes()

    r2 = runner.invoke(cli, ["completion", "install", "--shell", "bash", "--rc-file", str(rc)])
    assert r2.exit_code == 0
    assert rc.read_bytes().count(b"_OCTOP_COMPLETE") == 1


def test_completion_install_appends_to_utf8_rc_with_non_ascii(tmp_path: Path) -> None:
    # The reported crash: a UTF-8 rc file on a cp936 Windows session, where
    # Path.read_text() raised UnicodeDecodeError before appending anything.
    rc = tmp_path / ".bashrc"
    rc.write_bytes("# 中文备注：自定义补全\nalias ll='ls -al'\n".encode())

    runner = CliRunner()
    result = runner.invoke(cli, ["completion", "install", "--shell", "bash", "--rc-file", str(rc)])
    assert result.exit_code == 0, result.output
    assert "_OCTOP_COMPLETE" in rc.read_bytes().decode("utf-8")
