"""Tests for ``octop plugin install`` source resolution."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner
from octop_harness.plugins import PluginRegistry

from octop.cli.main import cli

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "plugins" / "echo-tool"


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    PluginRegistry.reset()
    yield
    PluginRegistry.reset()


def _echo_zip(dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w") as zf:
        for path in _FIXTURE.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=f"echo-tool/{path.relative_to(_FIXTURE).as_posix()}")
    return dest


def test_install_accepts_local_zip(tmp_octop_home: Path, tmp_path: Path) -> None:
    archive = _echo_zip(tmp_path / "echo-tool.zip")

    result = CliRunner().invoke(cli, ["plugin", "install", str(archive), "--force"])

    assert result.exit_code == 0, result.output
    assert "Installed plugin echo-tool" in result.output
    assert (tmp_octop_home / "plugins" / "echo-tool" / "plugin.yaml").is_file()


def test_install_accepts_local_directory(tmp_octop_home: Path) -> None:
    result = CliRunner().invoke(cli, ["plugin", "install", str(_FIXTURE), "--force"])

    assert result.exit_code == 0, result.output
    assert (tmp_octop_home / "plugins" / "echo-tool" / "plugin.yaml").is_file()


def test_install_rejects_local_non_zip_file(tmp_octop_home: Path, tmp_path: Path) -> None:
    bogus = tmp_path / "notes.txt"
    bogus.write_text("not a plugin", encoding="utf-8")

    result = CliRunner().invoke(cli, ["plugin", "install", str(bogus)])

    assert result.exit_code != 0
    assert not (tmp_octop_home / "plugins" / "echo-tool").exists()


def test_install_reports_missing_source(tmp_octop_home: Path, tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, ["plugin", "install", str(tmp_path / "missing.zip")])

    assert result.exit_code != 0
    assert "not a directory, ZIP file, or URL" in result.output
