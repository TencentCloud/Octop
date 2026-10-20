"""Tests for agent runtime env merge (process + workspace .env)."""

from __future__ import annotations

from pathlib import Path

from octop_harness.runtime_env import (
    is_protected_env_key,
    merge_host_stdio_env,
    overlay_env,
    parse_env_text,
    resolve_docker_execute_env,
    resolve_local_execute_env,
)


def test_parse_env_text_ignores_comments() -> None:
    parsed = parse_env_text('# x\nFOO=bar\nexport BAZ="a b"\n')
    assert parsed == {"FOO": "bar", "BAZ": "a b"}


def test_protected_keys() -> None:
    assert is_protected_env_key("HOME")
    assert is_protected_env_key("OCTOP_HOME")
    assert is_protected_env_key("OCTOP_DATABASE_URL")
    assert not is_protected_env_key("TAVILY_API_KEY")


def test_overlay_skips_protected_when_requested() -> None:
    out = overlay_env({"HOME": "/orig", "FOO": "1"}, {"HOME": "/hack", "FOO": "2"})
    assert out["HOME"] == "/orig"
    assert out["FOO"] == "2"


def test_resolve_local_execute_env_inherits_and_overlays(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("ADMIN_KEY", "from-process")  # type: ignore[attr-defined]
    monkeypatch.setenv("SHARED", "process")  # type: ignore[attr-defined]
    (tmp_path / ".env").write_text("SHARED=workspace\nAGENT_ONLY=1\nHOME=/nope\n", encoding="utf-8")
    env = resolve_local_execute_env(
        inherit=True,
        extra={"EXTRA": "yes"},
        workspace_dir=tmp_path,
    )
    assert env["ADMIN_KEY"] == "from-process"
    assert env["SHARED"] == "workspace"
    assert env["AGENT_ONLY"] == "1"
    assert env["EXTRA"] == "yes"
    assert env["HOME"] != "/nope"


def test_resolve_local_execute_env_prefers_workspace_reader(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("KEY=host\n", encoding="utf-8")
    env = resolve_local_execute_env(
        inherit=False,
        extra={"EXTRA": "x"},
        workspace_dir=tmp_path,
        workspace_reader=lambda: {"KEY": "backend"},
    )
    assert env["KEY"] == "backend"
    assert env["EXTRA"] == "x"


def test_resolve_local_execute_env_empty_reader_ignores_stale_host_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("STALE=1\n", encoding="utf-8")
    env = resolve_local_execute_env(
        inherit=False,
        workspace_dir=tmp_path,
        workspace_reader=lambda: {},
    )
    assert "STALE" not in env


def test_resolve_docker_execute_env_does_not_copy_host(monkeypatch: object) -> None:
    monkeypatch.setenv("SECRET_HOST", "leak")  # type: ignore[attr-defined]
    env = resolve_docker_execute_env(
        global_env={"TAVILY_API_KEY": "tvly"},
        workspace_env={"AGENT_ONLY": "1", "HOME": "/hack"},
    )
    assert "SECRET_HOST" not in env
    assert env["TAVILY_API_KEY"] == "tvly"
    assert env["AGENT_ONLY"] == "1"
    assert env["HOME"] == "/root"
    assert "PATH" in env


def test_resolve_docker_ignores_admin_path_and_home() -> None:
    env = resolve_docker_execute_env(
        global_env={"PATH": "/evil", "HOME": "/hack", "TAVILY_API_KEY": "tvly"},
        workspace_env={"PATH": "/workspace/bin"},
    )
    assert env["TAVILY_API_KEY"] == "tvly"
    assert env["HOME"] == "/root"
    assert env["PATH"] == "/workspace/bin"


def test_merge_host_stdio_env_is_subset_not_full_host(monkeypatch: object) -> None:
    monkeypatch.setenv("HOST_SECRET", "nope")  # type: ignore[attr-defined]
    monkeypatch.setenv("TAVILY_API_KEY", "tvly")  # type: ignore[attr-defined]
    env = merge_host_stdio_env({"TAVILY_API_KEY": "from-spec"})
    assert env["TAVILY_API_KEY"] == "from-spec"
    assert "HOST_SECRET" not in env
    assert "PATH" in env or "HOME" in env
