"""Tests for harness init command."""

from pathlib import Path

from click.testing import CliRunner

from octop_harness.cli.main import cli


def test_init_default_uses_global_home(tmp_path: Path, monkeypatch: object) -> None:
    """With no flags, init writes to ``~/.octop-harness/``. We point
    ``Path.home`` at a tmp dir so the test is hermetic."""
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))  # type: ignore[attr-defined]

    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0, result.output

    harness = fake_home / ".octop-harness"
    assert (harness / "config.json").is_file()
    assert (harness / "sessions").is_dir()
    assert (harness / "workspace" / "_builtin_skills" / ".version").is_file()


def test_init_default_config_uses_workspace_dir(tmp_path: Path, monkeypatch: object) -> None:
    """The seeded ``config.json`` must point ``workspace_dir`` at an
    absolute path inside the harness home, so the running agent's
    backend is rooted there by default."""
    import json

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))  # type: ignore[attr-defined]

    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0, result.output

    cfg = json.loads((fake_home / ".octop-harness" / "config.json").read_text())
    assert cfg["workspace_dir"] == str(fake_home / ".octop-harness" / "workspace")
    assert cfg["language"] == "en"
    assert "providers" in cfg
    # ``root_dir`` is no longer a top-level field — it has been folded
    # into the backend spec when relevant.
    assert "root_dir" not in cfg


def test_init_explicit_path(tmp_path: Path) -> None:
    """``--path`` takes precedence over ``--scope`` and global default."""
    target = tmp_path / "custom-home"

    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--path", str(target)])
    assert result.exit_code == 0, result.output

    assert (target / "config.json").is_file()
    assert (target / "workspace" / "_builtin_skills" / ".version").is_file()


def test_init_seeds_builtin_skills(tmp_path: Path) -> None:
    """Regression for the bug where ``cli init`` did not call the
    library's ``init_workspace`` and therefore never copied built-in
    skills."""
    runner = CliRunner()
    target = tmp_path / "fresh"
    result = runner.invoke(cli, ["init", "--path", str(target)])
    assert result.exit_code == 0, result.output

    builtin_skills = target / "workspace" / "_builtin_skills"
    assert builtin_skills.is_dir()
    assert (builtin_skills / ".version").is_file()

    skill_dirs = [p for p in builtin_skills.iterdir() if p.is_dir()]
    assert skill_dirs, "expected at least one built-in skill to be copied"
    assert any((d / "SKILL.md").is_file() for d in skill_dirs)


def test_init_seeds_markdown_templates(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "templated"
    result = runner.invoke(cli, ["init", "--path", str(target), "--language", "zh"])
    assert result.exit_code == 0, result.output

    workspace = target / "workspace"
    assert (workspace / "AGENTS.md").is_file()
    assert (workspace / "MEMORY.md").is_file()


def test_init_idempotent_does_not_clobber_config(tmp_path: Path) -> None:
    """Re-running ``init`` on a populated home must not overwrite
    the user's ``config.json``."""
    runner = CliRunner()
    target = tmp_path / "existing"
    target.mkdir()

    config_file = target / "config.json"
    config_file.write_text('{"providers": {"custom": "kept"}}', encoding="utf-8")

    result = runner.invoke(cli, ["init", "--path", str(target)])
    assert result.exit_code == 0, result.output

    assert config_file.read_text(encoding="utf-8") == '{"providers": {"custom": "kept"}}'
    assert (target / "workspace" / "_builtin_skills" / ".version").is_file()


def test_init_overwrite_flag_resyncs_skills(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "force"
    runner.invoke(cli, ["init", "--path", str(target)])
    version_file = target / "workspace" / "_builtin_skills" / ".version"
    version_file.write_text("stale", encoding="utf-8")

    result = runner.invoke(cli, ["init", "--path", str(target), "--overwrite"])
    assert result.exit_code == 0, result.output
    assert version_file.read_text(encoding="utf-8") != "stale"


def test_init_scope_project_uses_cwd(tmp_path: Path, monkeypatch: object) -> None:
    """``--scope project`` writes to ``<cwd>/.octop-harness/`` so users
    can keep workspace state per-repo."""
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))  # type: ignore[attr-defined]

    project = tmp_path / "myrepo"
    project.mkdir()
    monkeypatch.chdir(project)  # type: ignore[attr-defined]

    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--scope", "project"])
    assert result.exit_code == 0, result.output

    project_home = project / ".octop-harness"
    assert (project_home / "config.json").is_file()
    assert (project_home / "workspace" / "_builtin_skills" / ".version").is_file()
    # Global home should NOT have been touched.
    assert not (fake_home / ".octop-harness").exists()
