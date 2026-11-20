"""Tests for git binary resolution and workspace execution targets."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from octop.infra.git.binary import (
    MIN_GIT_VERSION,
    clear_git_binary_cache,
    resolve_git_binary,
)
from octop.infra.git.target import (
    HostGitTarget,
    SandboxGitTarget,
    spec_uses_docker,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="needs shell scripts")


def _fake_git(tmp_path: Path, version: str) -> Path:
    script = tmp_path / "git"
    script.write_text(f'#!/bin/sh\necho "git version {version}"\n')
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_git_binary_cache()


@posix_only
def test_preferred_binary_wins_with_source_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _fake_git(tmp_path, "2.43.0")
    monkeypatch.setattr("shutil.which", lambda _name: None)
    binary = resolve_git_binary(str(script))
    assert binary is not None
    assert (binary.path, binary.version, binary.source) == (
        str(script),
        (2, 43, 0),
        "config",
    )


@posix_only
def test_env_binary_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = _fake_git(tmp_path, "2.40.1")
    monkeypatch.setenv("OCTOP_GIT_BINARY", str(script))
    monkeypatch.setattr("shutil.which", lambda _name: None)
    binary = resolve_git_binary()
    assert binary is not None
    assert (binary.source, binary.version) == ("env", (2, 40, 1))


@posix_only
def test_too_old_binary_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = _fake_git(tmp_path, "2.20.0")
    assert MIN_GIT_VERSION > (2, 20, 0)
    monkeypatch.setattr("shutil.which", lambda _name: None)
    monkeypatch.setattr("octop.infra.git.binary._platform_candidates", lambda: [])
    assert resolve_git_binary(str(script)) is None


@posix_only
def test_non_executable_binary_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = _fake_git(tmp_path, "2.43.0")
    script.chmod(0o644)
    monkeypatch.setattr("shutil.which", lambda _name: None)
    monkeypatch.setattr("octop.infra.git.binary._platform_candidates", lambda: [])
    assert resolve_git_binary(str(script)) is None


def test_spec_uses_docker_nested() -> None:
    assert spec_uses_docker({"type": "docker"})
    assert spec_uses_docker({"type": "composite", "default": {"type": "docker"}, "routes": {}})
    assert spec_uses_docker(
        {
            "type": "composite",
            "default": {"type": "local_shell"},
            "routes": {"x": {"type": "docker"}},
        }
    )
    assert not spec_uses_docker({"type": "local_shell"})
    assert not spec_uses_docker(None)


async def test_sandbox_target_runs_git_in_container() -> None:
    class Response:
        output = "git version 2.43.0\n"
        exit_code = 0

    class Backend:
        def __init__(self) -> None:
            self.command = ""

        def execute(self, command: str, timeout: int | None = None) -> Response:
            self.command = command
            return Response()

    class Workspace:
        def __init__(self) -> None:
            self.backend = Backend()

        def exists(self, path: str) -> bool:
            return path == ".git"

        def read_text(self, path: str) -> str:
            return "content\n"

        def delete(self, path: str) -> None:
            self.deleted = path

    workspace = Workspace()
    target = SandboxGitTarget(workspace)
    code, out, _ = await target.run(["status"], timeout=5, max_bytes=64)
    assert code == 0
    assert b"git version" in out
    assert workspace.backend.command == "GIT_TERMINAL_PROMPT=0 git status"
    assert target.exists(".git")


async def test_host_target_reports_unavailable_without_binary(tmp_path: Path) -> None:
    target = HostGitTarget(tmp_path, None)
    assert not target.available
    assert not target.exists(".git")
    (tmp_path / "note.md").write_text("x\n")
    assert target.read_text("note.md") == "x\n"


async def test_sandbox_probe_reports_missing_git() -> None:
    class Response:
        output = "git: not found\n"
        exit_code = 127

    class Backend:
        def execute(self, command: str, timeout: int | None = None) -> Response:
            return Response()

    class Workspace:
        backend = Backend()

        def exists(self, path: str) -> bool:
            return path == ".git"

        def read_text(self, path: str) -> str | None:
            return None

        def delete(self, path: str) -> None:
            pass

    target = SandboxGitTarget(Workspace())
    assert await target.probe() is False
    assert target.available is False


async def test_host_status_without_binary_reports_unavailable(tmp_path: Path) -> None:
    from octop.infra.git.repo import get_status

    (tmp_path / ".git").mkdir()
    snapshot = await get_status(HostGitTarget(tmp_path, None))
    assert snapshot.is_repo is True
    assert snapshot.git_available is False
