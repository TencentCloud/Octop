"""Scoped ``root_dir`` backend alignment and bubblewrap jail tests.

``BubbledLocalShellBackend`` is constructed only when Linux + ``virtual_mode`` +
non-host ``root_dir`` + ``bwrap`` are available (factory routes before any
backend I/O). Otherwise ``HarnessLocalShellBackend`` runs on the host; with
``virtual_mode`` and a scoped ``root_dir`` it still rewrites virtual absolute
paths in ``execute`` onto that root (harness-agent >= 1.0).

Cross-platform cases run on Windows, macOS, and Linux. POSIX-shell and real
``bwrap`` jail cases are skipped where the host cannot run them (see markers).
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from unittest.mock import patch

from deepagents.backends.protocol import ExecuteResponse
from harness_agent.backends import resolve_backend
from harness_agent.backends.bwrap_shell import (
    BubbledLocalShellBackend,
    HarnessLocalShellBackend,
    can_use_bubbled_shell,
)

from tests.support.bwrap_marks import linux_bwrap_only, posix_shell_only

_BWRAP = "/usr/bin/bwrap"


def _scoped_spec(tmp_path: Path) -> tuple[dict[str, object], Path, Path]:
    scoped = tmp_path / "scoped_root"
    workspace = tmp_path / "agent_ws"
    scoped.mkdir()
    workspace.mkdir()
    spec: dict[str, object] = {
        "type": "local_shell",
        "root_dir": str(scoped),
        "virtual_mode": True,
    }
    return spec, scoped, workspace


def _unwrap(backend: object) -> object:
    return getattr(backend, "default", backend)


# ---------------------------------------------------------------------------
# Cross-platform (Windows + macOS + Linux)
# ---------------------------------------------------------------------------


def test_resolve_backend_routes_bubbled_only_when_jail_available(tmp_path: Path) -> None:
    """Factory chooses Bubbled vs HarnessLocalShell before any write/execute."""
    spec, scoped, workspace = _scoped_spec(tmp_path)

    with patch(
        "harness_agent.backends.bwrap_shell.resolve_bubbled_bwrap",
        return_value=_BWRAP,
    ):
        bubbled = resolve_backend(spec, workspace_dir=workspace)
    assert isinstance(bubbled, BubbledLocalShellBackend)
    assert bubbled._bwrap_path == _BWRAP
    assert Path(bubbled.cwd).resolve() == scoped.resolve()

    with patch(
        "harness_agent.backends.bwrap_shell.resolve_bubbled_bwrap",
        return_value=None,
    ):
        plain = resolve_backend(spec, workspace_dir=workspace)
    assert isinstance(plain, HarnessLocalShellBackend)
    assert not isinstance(plain, BubbledLocalShellBackend)
    assert Path(plain.cwd).resolve() == scoped.resolve()


def test_resolve_backend_host_root_is_never_bubbled(tmp_path: Path) -> None:
    workspace = tmp_path / "agent_ws"
    workspace.mkdir()
    spec = {"type": "local_shell", "root_dir": "/", "virtual_mode": True}
    backend = resolve_backend(spec, workspace_dir=workspace)
    inner = _unwrap(backend)
    assert isinstance(inner, HarnessLocalShellBackend)
    assert not isinstance(inner, BubbledLocalShellBackend)


def test_write_virtual_path_lands_under_scoped_root(tmp_path: Path) -> None:
    """Filesystem virtual ``/out/…`` maps under scoped ``root_dir`` on every OS."""
    spec, scoped, workspace = _scoped_spec(tmp_path)
    with patch(
        "harness_agent.backends.bwrap_shell.resolve_bubbled_bwrap",
        return_value=None,
    ):
        backend = resolve_backend(spec, workspace_dir=workspace)
    write = backend.write("/out/hello.txt", "hello-scoped")
    assert write.error is None
    assert (scoped / "out" / "hello.txt").read_text(encoding="utf-8") == "hello-scoped"


def test_read_virtual_path_from_scoped_root(tmp_path: Path) -> None:
    spec, scoped, workspace = _scoped_spec(tmp_path)
    with patch(
        "harness_agent.backends.bwrap_shell.resolve_bubbled_bwrap",
        return_value=None,
    ):
        backend = resolve_backend(spec, workspace_dir=workspace)
    target = scoped / "nested" / "note.txt"
    target.parent.mkdir(parents=True)
    target.write_text("read-me", encoding="utf-8")

    read = backend.read("/nested/note.txt")
    assert read.error is None
    assert read.file_data is not None
    assert "read-me" in read.file_data.get("content", "")


def test_execute_without_jail_rewrites_virtual_command_paths(tmp_path: Path) -> None:
    """Non-jail scoped shell still maps virtual absolute paths onto ``root_dir``.

    harness-agent 1.0 no longer delegates ``execute`` to deepagents
    ``LocalShellBackend.execute``; it rewrites then calls ``_execute_on_host``.
    Env mapping is stubbed so inaccessible ``PATH`` entries (common on CI)
    cannot raise ``PermissionError`` from ``Path.exists``.
    """
    spec, scoped, workspace = _scoped_spec(tmp_path)
    (scoped / "out").mkdir()
    with patch(
        "harness_agent.backends.bwrap_shell.resolve_bubbled_bwrap",
        return_value=None,
    ):
        backend = resolve_backend(spec, workspace_dir=workspace)
    assert isinstance(backend, HarnessLocalShellBackend)

    expected = str((scoped / "out" / "mapped.txt").resolve())
    with (
        patch.object(
            HarnessLocalShellBackend,
            "_execute_on_host",
            return_value=ExecuteResponse(output="ok", exit_code=0, truncated=False),
        ) as host_exec,
        patch(
            "harness_agent.backends.local_shell.map_virtual_paths_in_env",
            side_effect=lambda env, *_a, **_k: env,
        ),
    ):
        result = backend.execute("echo x > /out/mapped.txt")

    assert result.exit_code == 0
    assert host_exec.call_args.args[0] == f"echo x > {expected}"


# ---------------------------------------------------------------------------
# POSIX shell (Linux + macOS; skipped on Windows)
# ---------------------------------------------------------------------------


@posix_shell_only
def test_host_root_backend_execute_works(tmp_path: Path) -> None:
    """Host-root ``local_shell`` still executes on POSIX hosts without jail."""
    workspace = tmp_path / "agent_ws"
    workspace.mkdir()
    spec = {"type": "local_shell", "root_dir": "/", "virtual_mode": True}
    backend = resolve_backend(spec, workspace_dir=workspace)
    inner = _unwrap(backend)
    assert isinstance(inner, HarnessLocalShellBackend)
    assert not isinstance(inner, BubbledLocalShellBackend)

    marker = f"octop-bwrap-host-root-{uuid.uuid4().hex}"
    result = inner.execute(f"echo {marker}")
    assert result.exit_code == 0
    assert marker in result.output


# ---------------------------------------------------------------------------
# Linux + bwrap (real directory jail; skipped on Windows/macOS/no bwrap)
# ---------------------------------------------------------------------------


@linux_bwrap_only
def test_live_resolve_uses_bubbled_when_host_has_bwrap(tmp_path: Path) -> None:
    spec, scoped, workspace = _scoped_spec(tmp_path)
    assert can_use_bubbled_shell(virtual_mode=True, root_dir=scoped)
    backend = resolve_backend(spec, workspace_dir=workspace)
    assert isinstance(backend, BubbledLocalShellBackend)
    assert backend._bwrap_path


@linux_bwrap_only
def test_write_file_then_execute_cat_same_virtual_path(tmp_path: Path) -> None:
    spec, scoped, workspace = _scoped_spec(tmp_path)
    backend = resolve_backend(spec, workspace_dir=workspace)
    assert isinstance(backend, BubbledLocalShellBackend)

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
        spec, _scoped, workspace = _scoped_spec(tmp_path)
        backend = resolve_backend(spec, workspace_dir=workspace)
        assert isinstance(backend, BubbledLocalShellBackend)
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
