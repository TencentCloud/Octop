"""Linux-only integration tests for bubblewrap execute jail."""

from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from octop_harness.backends import resolve_backend
from octop_harness.backends.bwrap_shell import BubbledLocalShellBackend

_BWRAP = shutil.which("bwrap")


def _bwrap_usable() -> bool:
    """Return True when bwrap can create a user namespace (often false on CI)."""
    if _BWRAP is None:
        return False
    try:
        proc = subprocess.run(
            [_BWRAP, "--die-with-parent", "--unshare-user", "--uid", "0", "--gid", "0", "true"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError):
        return False
    return proc.returncode == 0


pytestmark = [
    pytest.mark.skipif(sys.platform != "linux", reason="bwrap jail is Linux-only"),
    pytest.mark.skipif(_BWRAP is None, reason="bwrap not installed"),
    pytest.mark.skipif(not _bwrap_usable(), reason="bwrap user namespace unavailable"),
]


def _backend(tmp_path: Path) -> BubbledLocalShellBackend:
    assert _BWRAP is not None
    return BubbledLocalShellBackend(
        root_dir=tmp_path,
        bwrap_path=_BWRAP,
        virtual_mode=True,
        inherit_env=True,
    )


def test_host_file_visible_via_virtual_path(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.txt").write_text("hello-jail", encoding="utf-8")
    result = backend.execute("cat /a/x.txt")
    assert result.exit_code == 0
    assert "hello-jail" in result.output


def test_execute_write_lands_under_root(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    result = backend.execute("mkdir -p /b && echo from-shell > /b/y.txt")
    assert result.exit_code == 0
    assert (tmp_path / "b" / "y.txt").read_text(encoding="utf-8").strip() == "from-shell"


def test_execute_starts_in_scoped_workspace(tmp_path: Path) -> None:
    assert _BWRAP is not None
    workspace = tmp_path / ".octop" / "workspaces" / "JAIL1"
    workspace.mkdir(parents=True)
    (workspace / "probe.sh").write_text("printf jail-workspace", encoding="utf-8")
    backend = BubbledLocalShellBackend(
        root_dir=tmp_path,
        workspace_dir=workspace,
        bwrap_path=_BWRAP,
        virtual_mode=True,
        inherit_env=True,
    )
    result = backend.execute("sh probe.sh && printf ':cwd=' && pwd")
    assert result.exit_code == 0
    assert "jail-workspace:cwd=/.octop/workspaces/JAIL1" in result.output


def test_factory_uses_bwrap_and_executes_scoped_script(tmp_path: Path) -> None:
    workspace = tmp_path / ".octop" / "workspaces" / "FACTORY1"
    workspace.mkdir(parents=True)
    (workspace / "probe.sh").write_text("printf factory-jail-ok", encoding="utf-8")
    backend = resolve_backend(
        {
            "type": "local_shell",
            "root_dir": str(tmp_path),
            "virtual_mode": True,
        },
        workspace_dir=workspace,
    )
    target = getattr(backend, "default", backend)
    assert isinstance(target, BubbledLocalShellBackend)
    result = backend.execute("sh probe.sh")
    assert result.exit_code == 0
    assert "factory-jail-ok" in result.output


def test_outside_root_not_visible(tmp_path: Path) -> None:
    secret = Path.home() / f".harness_bwrap_secret_{uuid.uuid4().hex}"
    secret.mkdir(parents=True)
    try:
        (secret / "nope.txt").write_text("secret", encoding="utf-8")
        backend = _backend(tmp_path)
        result = backend.execute(f"cat {secret}/nope.txt")
        assert result.exit_code != 0
    finally:
        shutil.rmtree(secret, ignore_errors=True)
