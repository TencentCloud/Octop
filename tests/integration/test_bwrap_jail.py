"""Scoped ``root_dir`` backend alignment and bubblewrap jail tests.

Cross-platform cases run on Windows, macOS, and Linux. POSIX-shell and real
``bwrap`` jail cases are skipped where the host cannot run them (see markers).
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse
from harness_agent.backends import resolve_backend
from harness_agent.backends.bwrap_shell import (
    BubbledLocalShellBackend,
    rewrite_virtual_paths_in_command,
)

from tests.support.bwrap_marks import linux_bwrap_only, posix_shell_only


def _scoped_backend(tmp_path: Path) -> tuple[BubbledLocalShellBackend, Path, Path]:
    """Octop-style scoped ``root_dir`` with a separate agent workspace."""
    scoped = tmp_path / "scoped_root"
    workspace = tmp_path / "agent_ws"
    scoped.mkdir()
    workspace.mkdir()
    spec = {
        "type": "local_shell",
        "root_dir": str(scoped),
        "virtual_mode": True,
    }
    backend = resolve_backend(spec, workspace_dir=workspace)
    assert isinstance(backend, BubbledLocalShellBackend)
    return backend, scoped, workspace


# ---------------------------------------------------------------------------
# Cross-platform (Windows + macOS + Linux)
# ---------------------------------------------------------------------------


def test_resolve_backend_uses_bubbled_local_shell(tmp_path: Path) -> None:
    backend, scoped, _workspace = _scoped_backend(tmp_path)
    assert Path(backend.cwd).resolve() == scoped.resolve()


def test_write_virtual_path_lands_under_scoped_root(tmp_path: Path) -> None:
    """Filesystem virtual ``/out/…`` maps under scoped ``root_dir`` on every OS."""
    backend, scoped, _workspace = _scoped_backend(tmp_path)
    write = backend.write("/out/hello.txt", "hello-scoped")
    assert write.error is None
    assert (scoped / "out" / "hello.txt").read_text(encoding="utf-8") == "hello-scoped"


def test_read_virtual_path_from_scoped_root(tmp_path: Path) -> None:
    backend, scoped, _workspace = _scoped_backend(tmp_path)
    target = scoped / "nested" / "note.txt"
    target.parent.mkdir(parents=True)
    target.write_text("read-me", encoding="utf-8")

    read = backend.read("/nested/note.txt")
    assert read.error is None
    assert read.file_data is not None
    assert "read-me" in read.file_data.get("content", "")


def test_execute_rewrites_virtual_paths_when_jail_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When bwrap is absent, execute rewrites ``/out/…`` onto scoped root (all OS)."""
    backend, scoped, _workspace = _scoped_backend(tmp_path)
    monkeypatch.setattr("harness_agent.backends.bwrap_shell.shutil.which", lambda _n: None)
    backend._bwrap_path = None
    backend._bwrap_disabled = False
    backend._missing_bwrap_warned = False

    with patch.object(
        LocalShellBackend,
        "execute",
        return_value=ExecuteResponse(output="ok", exit_code=0, truncated=False),
    ) as super_exec:
        result = backend.execute("echo x > /out/mapped.txt")

    assert result.exit_code == 0
    rewritten = super_exec.call_args.args[0]
    assert rewritten == rewrite_virtual_paths_in_command("echo x > /out/mapped.txt", scoped)


# ---------------------------------------------------------------------------
# POSIX shell (Linux + macOS; skipped on Windows)
# ---------------------------------------------------------------------------


@posix_shell_only
def test_execute_write_then_read_file_same_tree(tmp_path: Path) -> None:
    """Shell under scoped root lands files where virtual ``read`` expects them."""
    backend, scoped, _workspace = _scoped_backend(tmp_path)
    result = backend.execute("mkdir -p /b && echo from-shell > /b/y.txt")
    assert result.exit_code == 0
    assert (scoped / "b" / "y.txt").read_text(encoding="utf-8").strip() == "from-shell"

    read = backend.read("/b/y.txt")
    assert read.error is None
    assert read.file_data is not None
    assert "from-shell" in read.file_data.get("content", "")


@posix_shell_only
def test_execute_rewrites_virtual_paths_without_bwrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, scoped, _workspace = _scoped_backend(tmp_path)
    monkeypatch.setattr(
        "harness_agent.backends.bwrap_shell.shutil.which",
        lambda name: None if name == "bwrap" else shutil.which(name),
    )
    backend._bwrap_path = None
    backend._bwrap_disabled = False
    backend._missing_bwrap_warned = False

    result = backend.execute("mkdir -p /out && echo mapped > /out/mapped.txt")
    assert result.exit_code == 0
    assert (scoped / "out" / "mapped.txt").read_text(encoding="utf-8").strip() == "mapped"


@posix_shell_only
def test_host_root_backend_execute_works(tmp_path: Path) -> None:
    """Host-root ``local_shell`` still executes on POSIX hosts without jail."""
    workspace = tmp_path / "agent_ws"
    workspace.mkdir()
    spec = {"type": "local_shell", "root_dir": "/", "virtual_mode": True}
    backend = resolve_backend(spec, workspace_dir=workspace)
    inner = getattr(backend, "default", backend)
    assert isinstance(inner, BubbledLocalShellBackend)

    marker = f"octop-bwrap-host-root-{uuid.uuid4().hex}"
    result = inner.execute(f"echo {marker}")
    assert result.exit_code == 0
    assert marker in result.output


# ---------------------------------------------------------------------------
# Linux + bwrap (real directory jail; skipped on Windows/macOS/no bwrap)
# ---------------------------------------------------------------------------


@linux_bwrap_only
def test_write_file_then_execute_cat_same_virtual_path(tmp_path: Path) -> None:
    backend, scoped, _workspace = _scoped_backend(tmp_path)
    write = backend.write("/out/hello.txt", "hello-jail")
    assert write.error is None
    assert (scoped / "out" / "hello.txt").read_text(encoding="utf-8") == "hello-jail"

    result = backend.execute("cat /out/hello.txt")
    assert result.exit_code == 0
    assert "hello-jail" in result.output


@linux_bwrap_only
def test_jail_hides_host_home_paths(tmp_path: Path) -> None:
    secret = Path.home() / f".octop_bwrap_test_{uuid.uuid4().hex}"
    secret.mkdir(parents=True)
    try:
        (secret / "nope.txt").write_text("secret", encoding="utf-8")
        backend, _scoped, _workspace = _scoped_backend(tmp_path)
        result = backend.execute(f"cat {secret}/nope.txt")
        assert result.exit_code != 0
    finally:
        shutil.rmtree(secret, ignore_errors=True)


@linux_bwrap_only
def test_skill_dir_bind_when_workspace_differs_from_root(tmp_path: Path) -> None:
    scoped = tmp_path / "scoped_root"
    workspace = tmp_path / "agent_ws"
    scoped.mkdir()
    skill_dir = workspace / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "note.txt").write_text("skill-content", encoding="utf-8")

    spec = {
        "type": "local_shell",
        "root_dir": str(scoped),
        "virtual_mode": True,
    }
    backend = resolve_backend(spec, workspace_dir=workspace)
    assert isinstance(backend, BubbledLocalShellBackend)

    result = backend.execute("cat /skills/demo/note.txt")
    assert result.exit_code == 0
    assert "skill-content" in result.output


@linux_bwrap_only
def test_subprocess_run_invokes_real_bwrap(tmp_path: Path) -> None:
    """Smoke-test that system ``bwrap`` can bind a temp dir at ``/``."""
    import subprocess

    root = tmp_path / "jail_root"
    root.mkdir()
    marker = "octop-bwrap-smoke"
    bwrap = shutil.which("bwrap")
    assert bwrap is not None
    # Merged-/usr hosts expose /bin,/lib,/lib64 as symlinks into /usr; bind those
    # as symlinks (and always mount /usr) so the dynamic linker and /bin/sh resolve.
    argv = [
        bwrap,
        "--die-with-parent",
        "--bind",
        str(root),
        "/",
        "--ro-bind",
        "/usr",
        "/usr",
    ]
    for host, guest in (("/lib", "/lib"), ("/lib64", "/lib64"), ("/bin", "/bin")):
        path = Path(host)
        if path.is_symlink():
            argv.extend(["--symlink", os.readlink(host), guest])
        elif path.exists():
            argv.extend(["--ro-bind", host, guest])
    argv.extend(
        [
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
            "--chdir",
            "/",
            "--",
            "/bin/sh",
            "-c",
            f"echo {marker} > /smoke.txt",
        ]
    )
    result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert (root / "smoke.txt").read_text(encoding="utf-8").strip() == marker
