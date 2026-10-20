"""Tests for harness skill command."""

from pathlib import Path

from click.testing import CliRunner

from octop_harness.cli.main import cli


def test_skill_list_empty(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    runner = CliRunner()
    result = runner.invoke(cli, ["skill", "list"])
    assert result.exit_code == 0
    assert "No skills" in result.output


def test_skill_install_and_list(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    skill_src = tmp_path / "my-skill"
    skill_src.mkdir()
    (skill_src / "skill.md").write_text("# My Skill")

    runner = CliRunner()
    result = runner.invoke(cli, ["skill", "install", str(skill_src)])
    assert result.exit_code == 0
    assert "Installed" in result.output

    result = runner.invoke(cli, ["skill", "list"])
    assert "my-skill" in result.output


def test_skill_remove(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    skill_src = tmp_path / "removable"
    skill_src.mkdir()
    (skill_src / "index.md").write_text("test")

    runner = CliRunner()
    runner.invoke(cli, ["skill", "install", str(skill_src)])

    result = runner.invoke(cli, ["skill", "remove", "removable"])
    assert result.exit_code == 0
    assert "Removed" in result.output
