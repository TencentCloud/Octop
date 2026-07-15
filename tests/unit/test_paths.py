"""tests/unit/test_paths.py"""

from __future__ import annotations

from pathlib import Path

from octop.infra.utils.paths import PathLayout


def test_root_paths(tmp_path: Path):
    p = PathLayout(tmp_path / ".octop")
    assert p.root == tmp_path / ".octop"
    assert p.db == tmp_path / ".octop" / "octop.db"
    assert p.logs_dir == tmp_path / ".octop" / "logs"
    assert p.log == tmp_path / ".octop" / "logs" / "octop.log"
    assert p.config == tmp_path / ".octop" / "config.json"


def test_log_dir_creation(tmp_path: Path):
    p = PathLayout(tmp_path / ".octop")
    assert not (tmp_path / ".octop" / "logs").exists()
    p.ensure_logs_dir()
    assert (tmp_path / ".octop" / "logs").is_dir()
    assert p.log == tmp_path / ".octop" / "logs" / "octop.log"


def test_user_dir_uses_username(tmp_path: Path):
    p = PathLayout(tmp_path / ".octop")
    assert p.user_dir("alice") == tmp_path / ".octop" / "users" / "alice"


def test_agent_workspace(tmp_path: Path):
    p = PathLayout(tmp_path / ".octop")
    ws = p.agent_workspace("agent01")
    assert ws == tmp_path / ".octop" / "agents" / "agent01"


def test_ensure_root_creates_dir(tmp_path: Path):
    p = PathLayout(tmp_path / ".octop")
    p.ensure_root()
    assert (tmp_path / ".octop").is_dir()


def test_ensure_agent_workspace(tmp_path: Path):
    p = PathLayout(tmp_path / ".octop")
    # New global path
    out = p.ensure_agent_workspace("a1")
    assert out.is_dir()
    assert out == tmp_path / ".octop" / "agents" / "a1"


def test_backups_dir(tmp_path: Path) -> None:
    p = PathLayout(tmp_path / ".octop")
    assert p.backups_dir == tmp_path / ".octop" / "backups"
    assert p.ensure_backups_dir().is_dir()


def test_path_layout_from_env_defaults_to_dot_octop(monkeypatch) -> None:
    monkeypatch.delenv("OCTOP_HOME", raising=False)
    assert PathLayout.from_env().root == Path.home() / ".octop"


def test_path_layout_from_env_honors_octop_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    assert PathLayout.from_env().root == tmp_path
