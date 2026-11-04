"""Unit tests for workspace zip archives."""

from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from octop_harness.backends import resolve_backend
from octop_harness.backends.workspace import BackendWorkspace

from octop.infra.backup.workspace_archive import (
    WorkspaceImportMode,
    export_workspace_zip,
    import_workspace_zip,
)


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
async def test_export_includes_hidden_and_runtime_dirs(tmp_path: Path) -> None:
    """Workspace zip must pack the full tree, including ``.octop`` and ``outbound``.

    ``aglob("**/*")`` skips dotfiles, which previously left archives with only a
    handful of root markdown files.
    """
    home = tmp_path / "home"
    workspace_dir = home / ".octop" / "workspaces" / "AGT1"
    (workspace_dir / "outbound" / "shots").mkdir(parents=True)
    (workspace_dir / "inbound").mkdir(parents=True)
    (workspace_dir / ".octop" / "sessions").mkdir(parents=True)
    (workspace_dir / ".octop" / "skills" / "demo").mkdir(parents=True)

    (workspace_dir / "SOUL.md").write_bytes(b"soul")
    (workspace_dir / ".env").write_bytes(b"KEY=1")
    (workspace_dir / "outbound" / "shots" / "a.png").write_bytes(b"png")
    (workspace_dir / "inbound" / "upload.txt").write_bytes(b"up")
    (workspace_dir / ".octop" / "sessions" / "state.db").write_bytes(b"db")
    (workspace_dir / ".octop" / "skills" / "demo" / "SKILL.md").write_bytes(b"skill")
    (workspace_dir / ".git" / "objects").mkdir(parents=True)
    (workspace_dir / ".git" / "objects" / "pack").write_bytes(b"skip-me")

    backend = resolve_backend(
        {"type": "filesystem", "root_dir": str(home), "virtual_mode": True},
        workspace_dir=workspace_dir,
    )
    workspace = BackendWorkspace(backend, workspace_dir, system_files_path=".octop")

    blob = await export_workspace_zip(workspace)
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        names = set(zf.namelist())
        assert zf.read("SOUL.md") == b"soul"
        assert zf.read(".env") == b"KEY=1"
        assert zf.read("outbound/shots/a.png") == b"png"
        assert zf.read("inbound/upload.txt") == b"up"
        assert zf.read(".octop/sessions/state.db") == b"db"
        assert zf.read(".octop/skills/demo/SKILL.md") == b"skill"
    assert ".git/objects/pack" not in names


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
    """``replace`` must not wipe hidden state absent from older archives.

    New exports include ``.octop``, but clearing it on replace would still destroy
    sessions/auth when the uploaded zip is an older archive that omitted them.
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

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[Any]:
        self._files.update(files)
        return [SimpleNamespace(path=name, error=None) for name, _ in files]


@pytest.mark.asyncio
async def test_export_reads_remote_backend_over_stale_local_copy(tmp_path: Path) -> None:
    """A mountless backend must be read via the protocol, not from a stale local file."""
    (tmp_path / "AGENTS.md").write_bytes(b"stale local AGENTS.md")
    workspace = BackendWorkspace(_MountlessBackend({"/AGENTS.md": b"remote AGENTS.md"}), tmp_path)

    blob = await export_workspace_zip(workspace)
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        assert zf.read("AGENTS.md") == b"remote AGENTS.md"


@pytest.mark.asyncio
async def test_export_mountless_includes_hidden_via_aglob(tmp_path: Path) -> None:
    """Mountless backends without ``als`` still pack hidden paths via aglob fallback."""
    workspace = BackendWorkspace(
        _MountlessBackend(
            {
                "/SOUL.md": b"soul",
                "/.octop/sessions/x.db": b"db",
                "/outbound/a.txt": b"out",
            }
        ),
        tmp_path,
    )

    blob = await export_workspace_zip(workspace)
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        names = set(zf.namelist())
        assert names == {"SOUL.md", ".octop/sessions/x.db", "outbound/a.txt"}
        assert zf.read(".octop/sessions/x.db") == b"db"
        assert zf.read("outbound/a.txt") == b"out"


@pytest.mark.asyncio
async def test_import_skips_octop_builtin_skills(tmp_path: Path) -> None:
    """An archive must not plant entries under the Octop-owned ``_builtin_skills`` root.

    ``DELETE`` / ``move`` refuse that prefix, so a planted skill directory would be
    something the user cannot remove through the API, while ``sync_octop_builtin_skills``
    only prunes the names it retired itself.
    """
    ws = tmp_path / "ws"
    ws.mkdir()
    backend = LocalShellBackend(root_dir=str(ws), virtual_mode=False)
    workspace = BackendWorkspace(backend, ws)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("notes.md", "keep me")
        zf.writestr("_builtin_skills/evil/SKILL.md", "plant")
        zf.writestr(".octop/_builtin_skills/evil/SKILL.md", "plant")
    data = buf.getvalue()

    result = await import_workspace_zip(workspace, data, mode="merge", local_workspace_dir=None)

    assert (ws / "notes.md").read_bytes() == b"keep me"
    assert not (ws / "_builtin_skills").exists()
    assert not (ws / ".octop" / "_builtin_skills").exists()
    assert result["imported"] == 1
    assert any("_builtin_skills" in warning for warning in result["warnings"])


@pytest.mark.asyncio
@pytest.mark.parametrize("system_files_path", ["", ".octop", ".state/runtime"])
async def test_export_skips_only_octop_sqlite_shm(tmp_path: Path, system_files_path: str) -> None:
    files = {
        "memory.sqlite": b"memory db",
        "memory.sqlite-wal": b"memory wal",
        "memory.sqlite-shm": b"memory shm",
        "checkpoints.sqlite": b"checkpoints db",
        "checkpoints.sqlite-wal": b"checkpoints wal",
        "checkpoints.sqlite-shm": b"checkpoints shm",
    }
    system_dir = tmp_path / system_files_path
    system_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (system_dir / name).write_bytes(content)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "memory.sqlite-shm").write_bytes(b"user file")
    (system_dir / "other.sqlite-shm").write_bytes(b"other db")
    workspace = BackendWorkspace(
        LocalShellBackend(root_dir=str(tmp_path), virtual_mode=False),
        tmp_path,
        system_files_path=system_files_path,
    )

    blob = await export_workspace_zip(workspace)

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = set(zf.namelist())
        assert (Path(system_files_path) / "memory.sqlite-shm").as_posix() not in names
        assert (Path(system_files_path) / "checkpoints.sqlite-shm").as_posix() not in names
        for name in (
            "memory.sqlite",
            "memory.sqlite-wal",
            "checkpoints.sqlite",
            "checkpoints.sqlite-wal",
        ):
            assert zf.read((Path(system_files_path) / name).as_posix()) == files[name]
        assert zf.read("notes/memory.sqlite-shm") == b"user file"
        assert zf.read((Path(system_files_path) / "other.sqlite-shm").as_posix()) == b"other db"


@pytest.mark.asyncio
async def test_export_mountless_skips_legacy_and_current_sqlite_shm(tmp_path: Path) -> None:
    workspace = BackendWorkspace(
        _MountlessBackend(
            {
                "/memory.sqlite-shm": b"legacy shm",
                "/.octop/checkpoints.sqlite-shm": b"current shm",
                "/.octop/memory.sqlite-wal": b"wal",
                "/notes/checkpoints.sqlite-shm": b"user file",
            }
        ),
        tmp_path,
    )

    blob = await export_workspace_zip(workspace)

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert set(zf.namelist()) == {".octop/memory.sqlite-wal", "notes/checkpoints.sqlite-shm"}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["merge", "replace"])
@pytest.mark.parametrize("system_files_path", ["", ".octop", ".state/runtime"])
@pytest.mark.parametrize("locale", ["en", "zh"])
async def test_import_skips_sqlite_shm_and_counts_uploaded_files(
    tmp_path: Path, mode: WorkspaceImportMode, system_files_path: str, locale: str
) -> None:
    system_dir = tmp_path / system_files_path
    system_dir.mkdir(parents=True, exist_ok=True)
    (system_dir / "memory.sqlite-shm").write_bytes(b"live shm")
    backend = LocalShellBackend(root_dir=str(tmp_path), virtual_mode=False)
    workspace = BackendWorkspace(backend, tmp_path, system_files_path=system_files_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in ("memory.sqlite-shm", "checkpoints.sqlite-shm"):
            zf.writestr((Path(system_files_path) / name).as_posix(), b"stale shm")
        zf.writestr((Path(system_files_path) / "memory.sqlite").as_posix(), b"db")
        zf.writestr((Path(system_files_path) / "memory.sqlite-wal").as_posix(), b"wal")
        zf.writestr("notes/memory.sqlite-shm", b"user file")

    result = await import_workspace_zip(
        workspace, buf.getvalue(), mode=mode, local_workspace_dir=tmp_path, locale=locale
    )

    assert (system_dir / "memory.sqlite-shm").read_bytes() == b"live shm"
    assert not (system_dir / "checkpoints.sqlite-shm").exists()
    assert (system_dir / "memory.sqlite").read_bytes() == b"db"
    assert (system_dir / "memory.sqlite-wal").read_bytes() == b"wal"
    assert (tmp_path / "notes" / "memory.sqlite-shm").read_bytes() == b"user file"
    assert result["imported"] == 3
    expected_warning = (
        "Skipped 2 SQLite shared-memory file(s); SQLite regenerates them."
        if locale == "en"
        else "已跳过 2 个 SQLite 共享内存文件；SQLite 会自动重新生成。"
    )
    assert result["warnings"] == [expected_warning]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["merge", "replace"])
@pytest.mark.parametrize("shm_entry", [".octop/memory.sqlite-shm", ".OCTOP/MEMORY.SQLITE-SHM"])
async def test_import_with_active_sqlite_shared_memory(
    tmp_path: Path, mode: WorkspaceImportMode, shm_entry: str
) -> None:
    """Windows refuses truncating the memory-mapped SHM file (issue #2303)."""
    system_dir = tmp_path / ".octop"
    system_dir.mkdir()
    conn = sqlite3.connect(system_dir / "memory.sqlite")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE notes (body TEXT)")
        conn.execute("INSERT INTO notes VALUES ('keep me')")
        conn.commit()
        assert (system_dir / "memory.sqlite-shm").is_file()
        if not (tmp_path / shm_entry).exists():
            pytest.skip("archive entry is not a case alias on this filesystem")
        workspace = BackendWorkspace(
            LocalShellBackend(root_dir=str(tmp_path), virtual_mode=False),
            tmp_path,
            system_files_path=".octop",
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(shm_entry, b"stale shm")
            zf.writestr("new.txt", b"imported")

        result = await import_workspace_zip(
            workspace, buf.getvalue(), mode=mode, local_workspace_dir=tmp_path
        )

        assert result["imported"] == 1
        assert result["warnings"]
        assert (tmp_path / "new.txt").read_bytes() == b"imported"
        assert conn.execute("SELECT body FROM notes").fetchall() == [("keep me",)]
    finally:
        conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["merge", "replace"])
@pytest.mark.parametrize("system_files_path", ["", ".octop", ".state/runtime"])
async def test_import_preserves_local_sqlite_shm_case_aliases(
    tmp_path: Path, mode: WorkspaceImportMode, system_files_path: str
) -> None:
    """Both archive filtering and replace cleanup must preserve the live SHM."""
    system_dir = tmp_path / system_files_path.upper()
    system_dir.mkdir(parents=True, exist_ok=True)
    live = system_dir / "MEMORY.SQLITE-SHM"
    live.write_bytes(b"live shm")
    canonical = tmp_path / system_files_path / "memory.sqlite-shm"
    if not canonical.exists():
        pytest.skip("case-sensitive local filesystem")
    workspace = BackendWorkspace(
        LocalShellBackend(root_dir=str(tmp_path), virtual_mode=False),
        tmp_path,
        system_files_path=system_files_path,
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr((Path(system_files_path.upper()) / "MEMORY.SQLITE-SHM").as_posix(), b"stale")
        zf.writestr("notes/MEMORY.SQLITE-SHM", b"user file")

    result = await import_workspace_zip(
        workspace, buf.getvalue(), mode=mode, local_workspace_dir=tmp_path
    )

    assert live.read_bytes() == b"live shm"
    assert (tmp_path / "notes" / "MEMORY.SQLITE-SHM").read_bytes() == b"user file"
    assert result["imported"] == 1
    assert result["warnings"] == [
        "Skipped 1 SQLite shared-memory file(s); SQLite regenerates them."
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("system_files_path", ["", ".octop", ".state/runtime"])
async def test_export_skips_local_sqlite_shm_case_aliases(
    tmp_path: Path, system_files_path: str
) -> None:
    system_dir = tmp_path / system_files_path.upper()
    system_dir.mkdir(parents=True, exist_ok=True)
    (system_dir / "MEMORY.SQLITE-SHM").write_bytes(b"live shm")
    (system_dir / "CHECKPOINTS.SQLITE-SHM").write_bytes(b"checkpoint shm")
    if not (tmp_path / system_files_path / "memory.sqlite-shm").exists():
        pytest.skip("case-sensitive local filesystem")
    (system_dir / "memory.sqlite").write_bytes(b"db")
    (system_dir / "memory.sqlite-wal").write_bytes(b"wal")
    workspace = BackendWorkspace(
        LocalShellBackend(root_dir=str(tmp_path), virtual_mode=False),
        tmp_path,
        system_files_path=system_files_path,
    )

    blob = await export_workspace_zip(workspace)

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        prefix = Path(system_files_path.upper())
        assert set(zf.namelist()) == {
            (prefix / "memory.sqlite").as_posix(),
            (prefix / "memory.sqlite-wal").as_posix(),
        }
        assert zf.read((prefix / "memory.sqlite").as_posix()) == b"db"
        assert zf.read((prefix / "memory.sqlite-wal").as_posix()) == b"wal"


@pytest.mark.asyncio
async def test_mountless_sqlite_shm_filter_is_case_sensitive(tmp_path: Path) -> None:
    """A local alias must not change the semantics of case-sensitive remote keys."""
    (tmp_path / ".OCTOP").mkdir()
    (tmp_path / ".OCTOP" / "MEMORY.SQLITE-SHM").write_bytes(b"stale local copy")
    backend = _MountlessBackend({})
    workspace = BackendWorkspace(backend, tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(".octop/memory.sqlite-shm", b"managed shm")
        zf.writestr(".OCTOP/MEMORY.SQLITE-SHM", b"distinct remote file")

    result = await import_workspace_zip(workspace, buf.getvalue(), mode="merge")
    blob = await export_workspace_zip(workspace)

    assert result["imported"] == 1
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert zf.namelist() == [".OCTOP/MEMORY.SQLITE-SHM"]
        assert zf.read(".OCTOP/MEMORY.SQLITE-SHM") == b"distinct remote file"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["merge", "replace"])
@pytest.mark.parametrize("system_files_path", ["", ".octop", ".state/runtime"])
async def test_local_sqlite_shm_filter_preserves_distinct_case_sensitive_files(
    tmp_path: Path, mode: WorkspaceImportMode, system_files_path: str
) -> None:
    system_dir = tmp_path / system_files_path
    system_dir.mkdir(parents=True, exist_ok=True)
    live = system_dir / "memory.sqlite-shm"
    live.write_bytes(b"live shm")
    upper_entry = (Path(system_files_path.upper()) / "MEMORY.SQLITE-SHM").as_posix()
    if (tmp_path / upper_entry).exists():
        pytest.skip("case-insensitive local filesystem")
    workspace = BackendWorkspace(
        LocalShellBackend(root_dir=str(tmp_path), virtual_mode=False),
        tmp_path,
        system_files_path=system_files_path,
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(upper_entry, b"distinct user file")

    result = await import_workspace_zip(
        workspace, buf.getvalue(), mode=mode, local_workspace_dir=tmp_path
    )
    blob = await export_workspace_zip(workspace)

    assert live.read_bytes() == b"live shm"
    assert result["imported"] == 1
    assert result["warnings"] == []
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert zf.namelist() == [upper_entry]
        assert zf.read(upper_entry) == b"distinct user file"
