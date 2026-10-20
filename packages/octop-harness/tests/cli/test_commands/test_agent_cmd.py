"""Tests for octop-harness agent commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from octop_harness.cli.main import cli


def _write_config(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / ".octop-harness"
    cfg_dir.mkdir()
    cfg = cfg_dir / "config.json"
    data = {
        "providers": {"deepseek": {"base_url": "http://x", "api_key": "k", "models": [{"id": "deepseek-chat"}]}},
        "default_model": "deepseek/deepseek-chat",
        "workspace_dir": str(tmp_path / "ws"),
        "default_agent": "main",
        "agents": {"main": {"provider": "deepseek", "model": "deepseek-chat"}},
    }
    cfg.write_text(json.dumps(data))
    return cfg


def test_agent_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "create" in result.output
    assert "remove" in result.output
    assert "show" in result.output
    assert "set-default" in result.output


def test_agent_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "list"])
    assert result.exit_code == 0
    assert "main" in result.output


def test_agent_create_and_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "agent",
            "create",
            "code",
            "--provider",
            "deepseek",
            "--model",
            "deepseek-chat",
            "--workspace-dir",
            str(tmp_path / "code-ws"),
        ],
    )
    assert result.exit_code == 0
    assert "code" in result.output or "Created" in result.output or "✓" in result.output

    result = runner.invoke(cli, ["agent", "list"])
    assert "code" in result.output
    assert "main" in result.output


def test_agent_remove(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = _write_config(tmp_path)
    data = json.loads(cfg.read_text())
    data["agents"]["code"] = {"provider": "deepseek", "model": "deepseek-chat"}
    cfg.write_text(json.dumps(data))

    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "remove", "code", "--yes"])
    assert result.exit_code == 0

    result = runner.invoke(cli, ["agent", "list"])
    assert "code" not in result.output


def test_agent_remove_main_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "remove", "main", "--yes"])
    assert result.exit_code != 0


def test_agent_show(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "show", "main"])
    assert result.exit_code == 0
    assert "deepseek" in result.output
