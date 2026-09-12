"""Unit tests for workspace zip archives."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends import resolve_backend
from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.backup.workspace_archive import export_workspace_zip, import_workspace_zip


@pytest.mark.asyncio
async def test_export_and_merge_import(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_bytes(b"hello")
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "note.md").write_bytes(b"note")
    backend = LocalShellBackend(root_dir=str(tmp_path), virtual_mode=False)
    workspace = BackendWorkspace(backend, tmp_path)

    blob = await export_workspace_zip(workspace)
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        names = set(zf.namelist())
    assert "hello.txt" in names
    assert "dir/note.md" in names

    for path in tmp_path.rglob("*"):
        if path.is_file():
            path.unlink()
    for path in sorted(tmp_path.rglob("*"), reverse=True):
        if path.is_dir():
            path.rmdir()

    result = await import_workspace_zip(workspace, blob, mode="merge", local_workspace_dir=None)
    assert result["imported"] == 2
    assert (tmp_path / "hello.txt").read_bytes() == b"hello"


@pytest.mark.asyncio
async def test_replace_clears_local_dir(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "old.txt").write_text("old", encoding="utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("new.txt", "new")
    data = buf.getvalue()

    backend = LocalShellBackend(root_dir=str(ws), virtual_mode=False)
    workspace = BackendWorkspace(backend, ws)
    result = await import_workspace_zip(workspace, data, mode="replace", local_workspace_dir=ws)
    assert result["imported"] == 1
    assert not (ws / "old.txt").exists()
    assert (ws / "new.txt").read_bytes() == b"new"


@pytest.mark.asyncio
async def test_export_ignores_same_named_file_at_backend_root(tmp_path: Path) -> None:
    """A same-named file at the backend root must not shadow the workspace's own file.

    Regression: under ``virtual_mode`` with a scoped ``root_dir`` that contains the
    workspace, ``BackendWorkspace`` probed ``{root_dir}/{rel}`` before
    ``{workspace_dir}/{rel}``, so the archive carried the backend-root ``AGENTS.md``
    while the entry name still said ``AGENTS.md``.
    """
    home = tmp_path / "home"
    workspace_dir = home / ".octop" / "workspaces" / "AGT1"
    workspace_dir.mkdir(parents=True)

    (home / "AGENTS.md").write_bytes(b"backend-root AGENTS.md")
    (workspace_dir / "AGENTS.md").write_bytes(b"workspace AGENTS.md")
    (workspace_dir / "SOUL.md").write_bytes(b"workspace SOUL.md")

    backend = resolve_backend(
        {"type": "filesystem", "root_dir": str(home), "virtual_mode": True},
        workspace_dir=workspace_dir,
    )
    workspace = BackendWorkspace(backend, workspace_dir, system_files_path=".octop")

    blob = await export_workspace_zip(workspace)
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        assert zf.read("AGENTS.md") == b"workspace AGENTS.md"
        assert zf.read("SOUL.md") == b"workspace SOUL.md"


@pytest.mark.asyncio
async def test_replace_import_keeps_system_state(tmp_path: Path) -> None:
    """``replace`` must not delete state an archive can never carry.

    Hidden paths are outside the export glob, so ``.octop`` (sessions / skills /
    auth) is absent from every archive; clearing it on replace destroyed data that
    the import could not restore.
    """
    ws = tmp_path / "ws"
    (ws / ".octop" / "sessions").mkdir(parents=True)
    (ws / ".octop" / "sessions" / "state.db").write_bytes(b"SESSION DB")
    (ws / ".octop" / "auth").mkdir(parents=True)
    (ws / ".octop" / "auth" / "token.json").write_bytes(b"TOKEN")
    (ws / "old.txt").write_text("old", encoding="utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("new.txt", "new")
    data = buf.getvalue()

    backend = LocalShellBackend(root_dir=str(ws), virtual_mode=False)
    workspace = BackendWorkspace(backend, ws)
    result = await import_workspace_zip(workspace, data, mode="replace", local_workspace_dir=ws)

    assert result["imported"] == 1
    assert not (ws / "old.txt").exists()  # visible content is still replaced
    assert (ws / "new.txt").read_bytes() == b"new"
    assert (ws / ".octop" / "sessions" / "state.db").read_bytes() == b"SESSION DB"
    assert (ws / ".octop" / "auth" / "token.json").read_bytes() == b"TOKEN"


@pytest.mark.asyncio
async def test_export_reads_legacy_root_system_dir_from_workspace(tmp_path: Path) -> None:
    """A legacy root ``skills/`` must not be shadowed by the backend root either.

    ``workspace.resolve_path()`` re-maps ``skills/`` under ``system_files_path``
    (``.octop``), so probing it for a workspace that still keeps legacy root
    ``skills/`` misses and falls back to the shadowed relative read.
    """
    home = tmp_path / "home"
    workspace_dir = home / ".octop" / "workspaces" / "AGT1"
    (workspace_dir / "skills" / "demo").mkdir(parents=True)
    (home / "skills" / "demo").mkdir(parents=True)

    (home / "skills" / "demo" / "SKILL.md").write_bytes(b"backend-root SKILL")
    (workspace_dir / "skills" / "demo" / "SKILL.md").write_bytes(b"workspace SKILL")

    backend = resolve_backend(
        {"type": "filesystem", "root_dir": str(home), "virtual_mode": True},
        workspace_dir=workspace_dir,
    )
    workspace = BackendWorkspace(backend, workspace_dir, system_files_path=".octop")

    blob = await export_workspace_zip(workspace)
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        assert zf.read("skills/demo/SKILL.md") == b"workspace SKILL"


class _MountlessBackend:
    """Backend exposing no host mount, so its files live outside the local disk."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files

    async def aglob(self, pattern: str, path: str = "/") -> Any:  # noqa: ARG002
        return SimpleNamespace(
            error=None,
            matches=[{"path": name, "is_dir": False} for name in sorted(self._files)],
        )

    def download_files(self, paths: list[str]) -> list[Any]:
        return [
            SimpleNamespace(path=name, content=self._files.get(name), error=None) for name in paths
        ]


@pytest.mark.asyncio
async def test_export_reads_remote_backend_over_stale_local_copy(tmp_path: Path) -> None:
    """A mountless backend must be read via the protocol, not from a stale local file."""
    (tmp_path / "AGENTS.md").write_bytes(b"stale local AGENTS.md")
    workspace = BackendWorkspace(_MountlessBackend({"/AGENTS.md": b"remote AGENTS.md"}), tmp_path)

    blob = await export_workspace_zip(workspace)
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        assert zf.read("AGENTS.md") == b"remote AGENTS.md"
