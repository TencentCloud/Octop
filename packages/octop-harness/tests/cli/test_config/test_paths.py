"""Tests for octop_harness.cli.config.paths."""

from pathlib import Path

from octop_harness.cli.config.paths import CliPaths


def test_global_dir_uses_home(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))  # type: ignore[arg-type]
    paths = CliPaths(project_dir=tmp_path / "myproject")
    assert paths.global_dir == tmp_path / ".octop-harness"


def test_project_dir_uses_dot_harness(tmp_path: Path) -> None:
    paths = CliPaths(project_dir=tmp_path)
    assert paths.project_dir == tmp_path / ".octop-harness"


def test_global_config_file(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))  # type: ignore[arg-type]
    paths = CliPaths(project_dir=tmp_path)
    assert paths.global_config_file == tmp_path / ".octop-harness" / "config.json"


def test_project_config_file(tmp_path: Path) -> None:
    paths = CliPaths(project_dir=tmp_path)
    assert paths.project_config_file == tmp_path / ".octop-harness" / "config.json"


def test_credentials_file(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))  # type: ignore[arg-type]
    paths = CliPaths(project_dir=tmp_path)
    assert paths.credentials_file == tmp_path / ".octop-harness" / "credentials.json"


def test_sessions_dir_uses_project_when_present(tmp_path: Path, monkeypatch: object) -> None:
    """Project-level sessions dir wins when it exists on disk."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "fakehome"))  # type: ignore[attr-defined]
    paths = CliPaths(project_dir=tmp_path)
    project_sessions = tmp_path / ".octop-harness" / "sessions"
    project_sessions.mkdir(parents=True)
    assert paths.sessions_dir == project_sessions


def test_sessions_dir_falls_back_to_global(tmp_path: Path, monkeypatch: object) -> None:
    """When the project lacks a sessions/ subdir, default to the global one
    so the user gets a usable history without per-project setup."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "fakehome"))  # type: ignore[attr-defined]
    paths = CliPaths(project_dir=tmp_path)
    # No project sessions dir on disk.
    assert paths.sessions_dir == tmp_path / "fakehome" / ".octop-harness" / "sessions"


def test_global_workspace_dir(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))  # type: ignore[attr-defined]
    paths = CliPaths(project_dir=tmp_path)
    assert paths.global_workspace_dir == tmp_path / ".octop-harness" / "workspace"


def test_global_sessions_dir(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))  # type: ignore[attr-defined]
    paths = CliPaths(project_dir=tmp_path)
    assert paths.global_sessions_dir == tmp_path / ".octop-harness" / "sessions"
