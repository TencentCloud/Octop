"""Tests for `octop update`."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.infra.setup import self_update


def test_update_check_only_no_install(monkeypatch: pytest.MonkeyPatch) -> None:
    import octop.cli.commands.update as update_cmd

    monkeypatch.setattr(update_cmd, "fetch_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_cmd, "get_local_version", lambda: "0.1.0")
    monkeypatch.setattr(update_cmd, "get_editable_path", lambda: None)

    called: dict[str, bool] = {}

    def _fake_upgrade(**kw):
        called["ran"] = True
        return self_update.UpgradeResult(success=True)

    monkeypatch.setattr(update_cmd, "run_upgrade", _fake_upgrade)

    runner = CliRunner()
    result = runner.invoke(cli, ["update", "--check"])
    assert result.exit_code == 0
    assert "9.9.9" in result.output
    assert "ran" not in called


def test_update_yes_runs_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    import octop.cli.commands.update as update_cmd

    monkeypatch.setattr(update_cmd, "fetch_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_cmd, "get_local_version", lambda: "0.1.0")
    monkeypatch.setattr(update_cmd, "get_editable_path", lambda: None)
    monkeypatch.setattr(
        update_cmd, "resolve_venv_python", lambda: "/home/user/.octop/venv/bin/python"
    )

    called: dict[str, bool] = {}

    def _fake_upgrade(**kw):
        called["ran"] = True
        return self_update.UpgradeResult(success=True, installed_version="9.9.9")

    monkeypatch.setattr(update_cmd, "run_upgrade", _fake_upgrade)

    runner = CliRunner()
    result = runner.invoke(cli, ["update", "--yes"])
    assert result.exit_code == 0
    assert called.get("ran") is True
    assert "/home/user/.octop/venv/bin/python" in result.output


def test_update_already_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    import octop.cli.commands.update as update_cmd

    monkeypatch.setattr(update_cmd, "fetch_latest_pypi_version", lambda: "0.1.0")
    monkeypatch.setattr(update_cmd, "get_local_version", lambda: "0.1.0")
    monkeypatch.setattr(update_cmd, "get_editable_path", lambda: None)

    runner = CliRunner()
    result = runner.invoke(cli, ["update", "--check"])
    assert result.exit_code == 0
    assert "up to date" in result.output.lower()


def test_build_upgrade_command_uses_managed_venv_python() -> None:
    python = "/home/user/.octop/venv/bin/python"
    cmd = self_update.build_upgrade_command("uv", python, index_url="https://mirror.example/simple")
    assert cmd is not None
    assert "--python" in cmd
    assert python in cmd
    assert "--upgrade-package" in cmd
    assert "octop" in cmd
    assert "https://mirror.example/simple" in cmd
    assert "--target" not in cmd


def test_build_upgrade_command_green_packages_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    packages = tmp_path / "packages"
    packages.mkdir()
    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(packages))
    python = "/opt/octop/runtime/bin/python3"
    cmd = self_update.build_upgrade_command("uv", python)
    assert cmd is not None
    assert "--target" in cmd
    assert str(packages) in cmd


def test_resolve_venv_python_green_uses_current_interpreter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    packages = tmp_path / "packages"
    packages.mkdir()
    venv_python = tmp_path / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setenv("OCTOP_GREEN_PACKAGES", str(packages))
    monkeypatch.setattr(self_update.sys, "executable", "/bundled/python3")
    monkeypatch.setattr(self_update.sys, "prefix", "/usr")
    monkeypatch.setattr(self_update.sys, "base_prefix", "/usr")
    assert self_update.resolve_venv_python() == "/bundled/python3"


def test_resolve_venv_python_prefers_octop_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    venv_python = tmp_path / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(self_update.sys, "prefix", "/usr")
    monkeypatch.setattr(self_update.sys, "base_prefix", "/usr")
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)

    assert self_update.resolve_venv_python() == str(venv_python)


def test_update_editable_install_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    import octop.cli.commands.update as update_cmd

    monkeypatch.setattr(update_cmd, "fetch_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_cmd, "get_local_version", lambda: "0.1.0")
    monkeypatch.setattr(update_cmd, "get_editable_path", lambda: "/src/orca")

    runner = CliRunner()
    result = runner.invoke(cli, ["update", "--yes"])
    assert result.exit_code == 1
    assert "/src/orca" in result.output
