"""Tests for .env file path resolution and loading."""

from __future__ import annotations

from pathlib import Path

from octop_harness.cli.config.paths import CliPaths


def test_global_env_file_path(tmp_path: Path) -> None:
    """global_env_file should resolve to ~/.octop-harness/.env"""
    paths = CliPaths(project_dir=tmp_path)
    # monkeypatch Path.home is done in other tests; here just check structure
    assert paths.global_env_file.name == ".env"
    assert paths.global_env_file.parent.name == ".octop-harness"


def test_project_env_file_path(tmp_path: Path) -> None:
    """project_env_file should resolve to <project_dir>/.env"""
    paths = CliPaths(project_dir=tmp_path)
    assert paths.project_env_file == tmp_path / ".env"


def test_load_dotenv_files_prefers_project(tmp_path: Path, monkeypatch: object) -> None:
    """Project .env takes precedence over global .env."""
    from octop_harness.cli import load_dotenv_files

    # Create project .env with PROJECT_VAR
    project_env = tmp_path / ".env"
    project_env.write_text("PROJECT_VAR=from_project\n")

    # Create global .env dir + .env with GLOBAL_VAR
    global_dir = tmp_path / "home" / ".octop-harness"
    global_dir.mkdir(parents=True)
    (global_dir / ".env").write_text("GLOBAL_VAR=from_global\n")

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))  # type: ignore[attr-defined]
    monkeypatch.delenv("PROJECT_VAR", raising=False)  # type: ignore[attr-defined]
    monkeypatch.delenv("GLOBAL_VAR", raising=False)  # type: ignore[attr-defined]

    loaded = load_dotenv_files(tmp_path)

    import os

    assert loaded == project_env
    assert os.environ.get("PROJECT_VAR") == "from_project"
    assert os.environ.get("GLOBAL_VAR") is None  # global not loaded


def test_load_dotenv_files_falls_back_to_global(tmp_path: Path, monkeypatch: object) -> None:
    """Falls back to global .env when no project .env exists."""
    from octop_harness.cli import load_dotenv_files

    global_dir = tmp_path / "home" / ".octop-harness"
    global_dir.mkdir(parents=True)
    (global_dir / ".env").write_text("GLOBAL_ONLY=yes\n")

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))  # type: ignore[attr-defined]
    monkeypatch.delenv("GLOBAL_ONLY", raising=False)  # type: ignore[attr-defined]

    loaded = load_dotenv_files(tmp_path)

    import os

    assert loaded is not None
    assert loaded.name == ".env"
    assert os.environ.get("GLOBAL_ONLY") == "yes"


def test_load_dotenv_files_returns_none_when_none_exist(tmp_path: Path, monkeypatch: object) -> None:
    """Returns None silently when neither .env exists."""
    from octop_harness.cli import load_dotenv_files

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))  # type: ignore[attr-defined]

    loaded = load_dotenv_files(tmp_path)
    assert loaded is None


def test_load_dotenv_files_override_false_does_not_clobber(tmp_path: Path, monkeypatch: object) -> None:
    """override=False does not clobber existing env vars."""
    from octop_harness.cli import load_dotenv_files

    project_env = tmp_path / ".env"
    project_env.write_text("CLOBBER_TEST=from_file\n")

    monkeypatch.setenv("CLOBBER_TEST", "from_shell")  # type: ignore[attr-defined]
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))  # type: ignore[attr-defined]

    load_dotenv_files(tmp_path, override=False)

    import os

    assert os.environ.get("CLOBBER_TEST") == "from_shell"


def test_load_dotenv_files_override_true_clobbers(tmp_path: Path, monkeypatch: object) -> None:
    """override=True replaces existing env vars (reload semantics)."""
    from octop_harness.cli import load_dotenv_files

    project_env = tmp_path / ".env"
    project_env.write_text("RELOAD_VAR=new_value\n")

    monkeypatch.setenv("RELOAD_VAR", "old_value")  # type: ignore[attr-defined]
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))  # type: ignore[attr-defined]

    load_dotenv_files(tmp_path, override=True)

    import os

    assert os.environ.get("RELOAD_VAR") == "new_value"
