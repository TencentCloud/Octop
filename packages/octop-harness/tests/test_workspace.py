"""Tests for ``BackendWorkspace``."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from octop_harness.backends.workspace import (
    DEFAULT_MEMORY_FILES,
    BackendWorkspace,
)


@pytest.fixture
def fs_backend(tmp_path: Path) -> Any:
    from deepagents.backends import FilesystemBackend

    return FilesystemBackend(root_dir=str(tmp_path), virtual_mode=False)


class TestBackendWorkspace:
    def test_write_and_read_text(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        ws.write_text("hello.txt", "hi", force=True)
        assert ws.read_text("hello.txt") == "hi"

    def test_relative_path_prepends_workspace_dir(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        assert ws.resolve_path("SOUL.md") == str(tmp_path / "SOUL.md")

    def test_resolve_path_uses_default_when_path_is_none(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        assert ws.resolve_path(None, default="BOOTSTRAP.md") == str(tmp_path / "BOOTSTRAP.md")

    def test_resolve_path_explicit_overrides_default(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        assert ws.resolve_path("SOUL.md", default="BOOTSTRAP.md") == str(tmp_path / "SOUL.md")

    def test_resolve_path_requires_path_or_default(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        with pytest.raises(TypeError, match="requires path or default"):
            ws.resolve_path(None)

    def test_absolute_path_unchanged(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        assert ws.resolve_path("/etc/passwd") == "/etc/passwd"

    def test_tilde_expanded(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        expected = str((Path.home() / ".octop" / "test.md").resolve())
        assert ws.resolve_path("~/.octop/test.md") == expected

    def test_escape_rejected(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        with pytest.raises(PermissionError, match="outside workspace"):
            ws.resolve_path("../outside.txt")

    def test_read_failback_rejects_relative_escape(self, fs_backend: Any, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        ws = BackendWorkspace(fs_backend, tmp_path)

        with pytest.raises(PermissionError, match="outside workspace"):
            ws.materialize_local("../outside.txt")
        with pytest.raises(PermissionError, match="outside workspace"):
            ws.exists("../outside.txt")

    def test_exists(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        assert not ws.exists("missing.md")
        ws.write_text("present.md", "x", force=True)
        assert ws.exists("present.md")

    def test_materialize_local(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        ws.write_text("file.txt", "hello", force=True)
        local = ws.materialize_local("file.txt")
        assert local is not None
        assert local.read_text(encoding="utf-8") == "hello"

    def test_skill_paths_under_workspace_dir(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        assert ws.skill_paths() == [
            str(tmp_path / "_builtin_skills"),
            str(tmp_path / "skills"),
        ]

    def test_skill_paths_virtual_mode_are_agent_facing(self, tmp_path: Path) -> None:
        """Deepagents sources must not join host root_dir under virtual_mode."""
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "home"
        ws_host = root / ".octop" / "workspaces" / "NBR8CP"
        ws_host.mkdir(parents=True)
        (ws_host / ".octop" / "_builtin_skills").mkdir(parents=True)
        (ws_host / ".octop" / "skills").mkdir(parents=True)
        (ws_host / "skills").mkdir(parents=True)

        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, ws_host, system_files_path=".octop")

        paths = ws.skill_paths()
        assert paths == [
            "/.octop/workspaces/NBR8CP/.octop/_builtin_skills",
            "/.octop/workspaces/NBR8CP/skills",
            "/.octop/workspaces/NBR8CP/.octop/skills",
        ]
        assert not any(str(root) in path for path in paths)

        # Backend can list the virtual builtin root (regression for SkillsMiddleware).
        ls = backend.ls(paths[0])
        entries = ls.entries if hasattr(ls, "entries") else ls
        assert entries is not None or ls is not None
        # Empty dir is fine; path_not_found must not happen.
        if hasattr(ls, "error"):
            assert not ls.error

    def test_memory_paths_virtual_mode_are_agent_facing(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "home"
        ws_host = root / ".octop" / "workspaces" / "NBR8CP"
        ws_host.mkdir(parents=True)
        (ws_host / "AGENTS.md").write_text("# rules", encoding="utf-8")

        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, ws_host)
        assert ws.memory_paths(["AGENTS.md"]) == ["/.octop/workspaces/NBR8CP/AGENTS.md"]

    def test_memory_paths_only_existing(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        (tmp_path / "AGENTS.md").write_text("# rules", encoding="utf-8")
        memory = ws.memory_paths(DEFAULT_MEMORY_FILES)
        assert memory == [str(tmp_path / "AGENTS.md")]

    def test_memory_paths_can_keep_missing_sources(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        paths = ws.memory_paths(DEFAULT_MEMORY_FILES, include_missing=True)
        assert paths == [str(tmp_path / name) for name in DEFAULT_MEMORY_FILES]
        assert ws.memory_paths() == []

    def test_missing_memory_sources_use_virtual_workspace_paths(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "home"
        workspace = root / "agents" / "example"
        workspace.mkdir(parents=True)
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace, system_files_path=".octop")
        assert ws.memory_paths(["MEMORY.md"], include_missing=True) == ["/agents/example/MEMORY.md"]

    def test_init_workspace_seeds_templates(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        result = ws.init_workspace(language="en", include_skills=False)
        assert result.workspace_path == str(tmp_path)
        assert (tmp_path / "AGENTS.md").is_file()
        assert str(tmp_path / "AGENTS.md") in result.templates_created

    def test_download_bytes(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        ws.upload_bytes("bin.dat", b"\x00\x01")
        assert ws.download_bytes("bin.dat") == b"\x00\x01"
        assert ws.download_bytes("missing.bin") is None

    def test_list_dir_root(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        (tmp_path / "SOUL.md").write_text("x", encoding="utf-8")
        entries = ws.list_dir(".")
        assert entries is not None
        paths = {entry["path"] if isinstance(entry, dict) else entry.path for entry in entries}
        assert "SOUL.md" in paths

    def test_upload_many(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        ws.upload_many([("a.txt", b"a"), ("nested/b.txt", b"b")])
        assert ws.read_text("a.txt") == "a"
        assert ws.read_text("nested/b.txt") == "b"


class TestBackendWorkspaceAsync:
    async def test_aexists_and_aread_text(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        assert not await ws.aexists("nope.md")
        await ws.awrite_text("USER.md", "hello")
        assert await ws.aexists("USER.md")
        assert await ws.aread_text("USER.md") == "hello"

    async def test_adownload_and_aupload_bytes(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        await ws.aupload_bytes("outbound/pic.png", b"png")
        assert await ws.adownload_bytes("outbound/pic.png") == b"png"

    async def test_aupload_many(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        await ws.aupload_many([("x.md", b"x"), ("y.md", b"y")])
        assert await ws.aread_text("x.md") == "x"
        assert await ws.aread_text("y.md") == "y"

    async def test_aupload_many_uses_native_backend_async_upload(self, tmp_path: Path) -> None:
        from unittest.mock import AsyncMock, MagicMock

        backend = MagicMock()
        backend.virtual_mode = True
        backend.cwd = tmp_path
        backend.root_dir = tmp_path
        backend.aupload_files = AsyncMock(return_value=[MagicMock(error=None)])
        backend.upload_files = MagicMock(return_value=[])
        ws = BackendWorkspace(backend, tmp_path)

        await ws.aupload_many([("x.md", b"x")])

        backend.aupload_files.assert_awaited_once_with([("/x.md", b"x")])
        backend.upload_files.assert_not_called()

    def test_relative_key_uses_workspace_dir_when_backend_has_no_mount(self, tmp_path: Path) -> None:
        from types import SimpleNamespace

        workspace_dir = tmp_path / "from-db"
        workspace_dir.mkdir()
        backend = SimpleNamespace(virtual_mode=False, cwd=None, root_dir=None)
        ws = BackendWorkspace(backend, workspace_dir)  # type: ignore[arg-type]
        assert ws._backend_storage_key(".octop/avatar.png") == "/.octop/avatar.png"
        assert str(workspace_dir) not in (ws._backend_storage_key("SOUL.md") or "")

    def test_cloud_storage_nests_under_virtual_workspace_folder(self, tmp_path: Path) -> None:
        from octop_harness.backends.cloud_storage_base import CloudStorageBackend
        from octop_harness.backends.workspace import remote_workspace_virtual_root

        class _StubCloud(CloudStorageBackend):
            def _prefix(self) -> str:
                return ""

            def _get_file_data(self, path: str) -> Any:
                return None

            def _put_file_data(self, path: str, file_data: Any) -> None:
                return None

            def _ls_entries(self, path: str) -> list[Any]:
                return []

            def _collect_recursive(self, path: str) -> dict[str, Any]:
                return {}

            def _iter_prefix_object_keys(self, path: str) -> Any:
                return iter(())

            def _prefix_has_objects(self, path: str) -> bool:
                return False

            def _copy_object(self, src: str, dest: str) -> None:
                return None

            def _put_dir_marker(self, virtual_dir: str) -> None:
                return None

            def delete_object(self, path: str) -> None:
                return None

            def delete_prefix(self, path: str) -> int:
                return 0

        workspace_dir = tmp_path / "AGT1B2"
        workspace_dir.mkdir()
        ws = BackendWorkspace(_StubCloud(), workspace_dir)
        virt = remote_workspace_virtual_root(workspace_dir)
        assert virt == "/.octop/workspaces/AGT1B2"
        assert ws._backend_storage_key("SOUL.md") == f"{virt}/SOUL.md"
        assert ws._backend_storage_key(".") == virt
        assert ws._backend_storage_key("skills/demo/SKILL.md") == f"{virt}/skills/demo/SKILL.md"
        assert str(workspace_dir) not in (ws._backend_storage_key("SOUL.md") or "")
        assert ws._backend_storage_key(str(workspace_dir / "SOUL.md")) == f"{virt}/SOUL.md"
        assert ws._mutation_storage_key("skills") == f"{virt}/skills"
        assert ws.present_path(f"{virt}/SOUL.md") == "SOUL.md"

    async def test_aupload_many_sync_fallback_reports_upload_files(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        backend = MagicMock()
        backend.virtual_mode = True
        backend.cwd = tmp_path
        backend.root_dir = tmp_path
        backend.aupload_files = None
        backend.upload_files = MagicMock(return_value=[MagicMock(error="boom")])
        ws = BackendWorkspace(backend, tmp_path)

        with pytest.raises(RuntimeError, match=r"backend upload_files error"):
            await ws.aupload_many([("x.md", b"x")])

    async def test_als_default_is_workspace_dot(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        (tmp_path / "AGENTS.md").write_text("#", encoding="utf-8")
        result = await ws.als()
        assert result is not None
        assert result.error is None
        assert result.entries

    async def test_als_dot_lists_workspace(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        (tmp_path / "SOUL.md").write_text("#", encoding="utf-8")
        result = await ws.als(".")
        assert result is not None
        assert result.error is None
        assert result.entries

    async def test_aglob_and_agrep(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        await ws.awrite_text("findme.md", "needle here")
        globbed = await ws.aglob("*.md", ".")
        assert globbed is not None
        assert globbed.matches
        assert all((m.get("path") if isinstance(m, dict) else m.path) == "findme.md" for m in globbed.matches)
        grep = await ws.agrep("needle", ".")
        assert grep is not None
        assert grep.matches
        assert grep.matches[0]["path"] == "findme.md"


class TestBackendWorkspaceMkdir:
    def test_mkdir_creates_directory(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        ws.mkdir("nested/deep")
        assert (tmp_path / "nested" / "deep").is_dir()
        entries = ws.list_dir("nested")
        assert entries is not None
        paths = {entry["path"] if isinstance(entry, dict) else entry.path for entry in entries}
        assert "nested/deep" in paths or "deep" in paths

    def test_mkdir_idempotent(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        ws.mkdir("same")
        ws.mkdir("same")
        assert (tmp_path / "same").is_dir()

    def test_mkdir_existing_file_raises(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        ws.write_text("file.md", "x", force=True)
        with pytest.raises(FileExistsError):
            ws.mkdir("file.md")

    def test_mkdir_unsupported_backend(self) -> None:
        from deepagents.backends import StateBackend

        from octop_harness.backends.utils import BackendOperationNotSupportedError

        ws = BackendWorkspace(StateBackend(), Path("/tmp/unused"))
        with pytest.raises(BackendOperationNotSupportedError, match="mkdir"):
            ws.mkdir("foo")

    async def test_amkdir(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        await ws.amkdir("async-dir")
        assert (tmp_path / "async-dir").is_dir()

    async def test_mkdir_virtual_local_shell_lists_parent(self, tmp_path: Path) -> None:
        from deepagents.backends.local_shell import LocalShellBackend

        backend = LocalShellBackend(root_dir="/", virtual_mode=True)
        backend.cwd = tmp_path.resolve()
        ws = BackendWorkspace(backend, tmp_path)
        await ws.amkdir("projects/demo")
        result = await ws.als("projects")
        assert result is not None
        assert result.error is None
        names = {row["path"].rstrip("/").rsplit("/", 1)[-1] for row in result.entries or []}
        assert "demo" in names


class TestBackendWorkspaceDeleteMove:
    def test_mkdir_and_delete_delegate_with_backend_storage_keys(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        backend = MagicMock()
        backend.mkdir_path = MagicMock()
        backend.delete_path = MagicMock()
        backend.root_dir = str(tmp_path)
        ws = BackendWorkspace(backend, tmp_path)

        ws.mkdir("nested")
        ws.delete("nested")

        backend.mkdir_path.assert_called_once_with("/nested")
        backend.delete_path.assert_called_once_with("/nested")

    def test_delete_file(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        ws.write_text("gone.md", "bye", force=True)
        assert ws.exists("gone.md")
        ws.delete("gone.md")
        assert not ws.exists("gone.md")

    def test_delete_directory(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        ws.upload_many([("nested/a.txt", b"a"), ("nested/b.txt", b"b")])
        ws.delete("nested")
        assert not ws.exists("nested/a.txt")

    def test_delete_missing_raises(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        with pytest.raises(FileNotFoundError):
            ws.delete("missing.md")

    def test_move_file(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        ws.write_text("src.md", "content", force=True)
        ws.move("src.md", "dest.md")
        assert not ws.exists("src.md")
        assert ws.read_text("dest.md") == "content"

    def test_move_rename_in_subdirectory(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        ws.upload_bytes("sub/old.txt", b"x")
        ws.move("sub/old.txt", "sub/new.txt")
        assert ws.read_text("sub/new.txt") == "x"

    def test_delete_unsupported_backend(self) -> None:
        from deepagents.backends import StateBackend

        from octop_harness.backends.utils import BackendOperationNotSupportedError

        ws = BackendWorkspace(StateBackend(), Path("/tmp/unused"))
        with pytest.raises(BackendOperationNotSupportedError, match="delete"):
            ws.delete("foo.md")

    async def test_adelete_and_amove(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        await ws.awrite_text("async.md", "hi")
        await ws.amove("async.md", "moved.md")
        assert await ws.aread_text("moved.md") == "hi"
        await ws.adelete("moved.md")
        assert not await ws.aexists("moved.md")

    def test_move_directory(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path)
        ws.upload_many([("src/a.txt", b"a"), ("src/b.txt", b"b")])
        ws.move("src", "dst")
        assert ws.read_text("dst/a.txt") == "a"
        assert ws.read_text("dst/b.txt") == "b"
        with pytest.raises(FileNotFoundError):
            ws.delete("src")

    async def test_delete_virtual_local_shell(self, tmp_path: Path) -> None:
        from deepagents.backends.local_shell import LocalShellBackend

        backend = LocalShellBackend(root_dir=str(tmp_path), virtual_mode=True)
        ws = BackendWorkspace(backend, tmp_path)
        await ws.aupload_bytes("SOUL.md", b"# soul")
        assert await ws.aexists("SOUL.md")
        await ws.adelete("SOUL.md")
        assert not await ws.aexists("SOUL.md")

    def test_move_delegates_to_backend_move_path(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        backend = MagicMock()
        backend.move_path = MagicMock()
        backend.root_dir = str(tmp_path)

        ws = BackendWorkspace(backend, tmp_path)
        ws.move("sub/old.txt", "sub/new.txt")
        backend.move_path.assert_called_once_with("/sub/old.txt", "/sub/new.txt")


class TestRelativeVirtualPath:
    def test_relative_virtual_path(self) -> None:
        from octop_harness.backends.utils import relative_virtual_path

        assert relative_virtual_path("/sub/a.txt", "/sub") == "a.txt"
        assert relative_virtual_path("/sub", "/sub") == ""
        assert relative_virtual_path("/subfolder/a.txt", "/sub") is None
        assert relative_virtual_path("/other/a.txt", "/sub") is None


class TestBackendWorkspaceVirtualMode:
    """``virtual_mode=True`` must not nest host-absolute workspace paths under root."""

    def test_non_force_relative_write_does_not_overwrite_workspace_file(
        self,
        tmp_path: Path,
    ) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        target = workspace / "SOUL.md"
        target.write_text("keep", encoding="utf-8")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)

        with pytest.raises(OSError, match="already exists"):
            ws.write_text("SOUL.md", "overwrite", force=False)

        assert target.read_text(encoding="utf-8") == "keep"

    def test_relative_write_lands_in_workspace_when_root_equals_ws(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
        ws = BackendWorkspace(backend, tmp_path)
        ws.write_text("SOUL.md", "soul", force=True)
        assert (tmp_path / "SOUL.md").read_text(encoding="utf-8") == "soul"
        assert not (tmp_path / "private").exists()
        assert ws.read_text("SOUL.md") == "soul"

    def test_relative_write_lands_in_workspace_when_backend_mount_differs(
        self,
        tmp_path: Path,
    ) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        ws.write_text("SOUL.md", "soul", force=True)
        assert (workspace / "SOUL.md").read_text(encoding="utf-8") == "soul"
        assert list(root.rglob("SOUL.md")) == []

    def test_virtual_absolute_resolve_and_materialize(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        (root / "generated").mkdir()
        target = root / "generated" / "deck.pptx"
        target.write_bytes(b"pptx")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        resolved = ws.resolve_path("/generated/deck.pptx")
        assert Path(resolved) == target.resolve()
        local = ws.materialize_local("/generated/deck.pptx")
        assert local is not None
        assert local.resolve() == target.resolve()

    def test_materialize_relative_prefers_root_then_workspace(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        (root / "deck.pptx").write_bytes(b"from-root")
        (workspace / "deck.pptx").write_bytes(b"from-ws")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        local = ws.materialize_local("deck.pptx")
        assert local is not None
        assert local.read_bytes() == b"from-root"

    def test_materialize_absolute_virtual_then_original_host(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        host_only = workspace / "only_host.bin"
        host_only.write_bytes(b"host-bytes")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        local = ws.materialize_local(str(host_only))
        assert local is not None
        assert local.resolve() == host_only.resolve()

    def test_materialize_absolute_prefers_virtual_nest_when_both_exist(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        host = workspace / "deck.pptx"
        host.write_bytes(b"host-deck")
        nest = root / Path(*host.parts[1:])
        nest.parent.mkdir(parents=True, exist_ok=True)
        nest.write_bytes(b"nested-deck")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        local = ws.materialize_local(str(host))
        assert local is not None
        assert local.resolve() == nest.resolve()
        assert local.read_bytes() == b"nested-deck"

    def test_download_bytes_uses_materialize_failback(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        hostish = "/Users/demo/only_nest.pptx"
        nest = root / "Users/demo/only_nest.pptx"
        nest.parent.mkdir(parents=True)
        nest.write_bytes(b"nest-bytes")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        assert ws.download_bytes(hostish) == b"nest-bytes"
        assert ws.read_text(hostish) == "nest-bytes"

    async def test_aread_text_uses_materialize_failback(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        hostish = "/Users/demo/page.html"
        nest = root / "Users/demo/page.html"
        nest.parent.mkdir(parents=True)
        nest.write_text("<html>ok</html>", encoding="utf-8")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        assert await ws.aread_text(hostish) == "<html>ok</html>"

    async def test_aexists_uses_original_host_path_failback(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        host_only = tmp_path / "host-only.bin"
        host_only.write_bytes(b"host")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)

        assert ws.exists(str(host_only))
        assert await ws.aexists(str(host_only))

    def test_list_dir_subdir_returns_workspace_relative_paths(self, tmp_path: Path) -> None:
        """Dashboard expects ``skills/demo``, not bare ``demo`` (avoids /demo 404)."""
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        (workspace / "skills" / "demo").mkdir(parents=True)
        (workspace / "skills" / "demo" / "SKILL.md").write_text("x", encoding="utf-8")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        entries = ws.list_dir("skills")
        assert entries is not None
        paths = {e["path"] if isinstance(e, dict) else e.path for e in entries}
        assert paths == {"skills/demo"}

    def test_host_absolute_under_virtual_maps_into_root(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        hostish = "/Users/demo/.octop/agents/X/generated/out.pptx"
        resolved = Path(ws.resolve_path(hostish))
        assert resolved == (root / "Users/demo/.octop/agents/X/generated/out.pptx").resolve()

    def test_mkdir_virtual_absolute_lands_in_backend_mount(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        ws.mkdir("/output")
        assert (root / "output").is_dir()
        assert not (workspace / "output").exists()

    def test_delete_virtual_absolute_from_backend_mount(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        target = root / "generated" / "out.pptx"
        target.parent.mkdir()
        target.write_bytes(b"pptx")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)

        ws.delete("/generated/out.pptx")

        assert not target.exists()

    def test_move_workspace_relative_to_virtual_absolute(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        (workspace / "file.txt").write_text("hi", encoding="utf-8")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        ws.move("file.txt", "/output/result.txt")
        assert (root / "output" / "result.txt").read_text(encoding="utf-8") == "hi"
        assert not (workspace / "file.txt").exists()
        assert not (workspace / "output" / "result.txt").exists()

    def test_move_both_workspace_relative_stays_in_workspace(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        (workspace / "a.txt").write_text("x", encoding="utf-8")
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        ws.move("a.txt", "b.txt")
        assert (workspace / "b.txt").read_text(encoding="utf-8") == "x"
        assert list(root.rglob("*.txt")) == []

    def test_move_workspace_directory_into_descendant_is_rejected(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        root = tmp_path / "root"
        workspace = tmp_path / "workspace"
        root.mkdir()
        workspace.mkdir()
        (workspace / "source").mkdir()
        backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)

        with pytest.raises(ValueError, match="own descendant"):
            ws.move("source", "source/nested")

    def test_read_text_prefers_remote_backend_over_stale_workspace_file(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        from deepagents.backends.protocol import ReadResult

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "AGENTS.md").write_text("stale-local", encoding="utf-8")

        backend = MagicMock()
        backend.virtual_mode = True
        backend.cwd = None
        backend.root_dir = None
        backend.read.return_value = ReadResult(file_data={"content": "from-remote"}, error=None)

        ws = BackendWorkspace(backend, workspace)
        assert ws.read_text("AGENTS.md") == "from-remote"
        backend.read.assert_called_once()

    def test_exists_uses_remote_backend_when_no_local_mount(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        backend = MagicMock()
        backend.virtual_mode = True
        backend.cwd = None
        backend.root_dir = None

        ws = BackendWorkspace(backend, workspace)
        with patch("octop_harness.backends.workspace.backend_file_exists", return_value=True) as exists_fn:
            assert ws.exists("AGENTS.md") is True
        exists_fn.assert_called_once()


class TestBackendWorkspacePresentPaths:
    async def test_als_strips_host_prefix_for_virtual_local_shell(self, tmp_path: Path) -> None:
        from deepagents.backends.local_shell import LocalShellBackend

        backend = LocalShellBackend(root_dir=str(tmp_path), virtual_mode=True)
        ws = BackendWorkspace(backend, tmp_path)
        await ws.aupload_bytes("SOUL.md", b"# soul")
        await ws.aupload_bytes("skills/foo/SKILL.md", b"skill")

        result = await ws.als(".")
        assert result is not None
        paths = {row["path"].rstrip("/") for row in result.entries or []}
        assert paths == {"SOUL.md", "skills"}

        content = await ws.aread_text("SOUL.md")
        assert content == "# soul"

        sub = await ws.als("skills")
        assert sub is not None
        sub_paths = {row["path"].rstrip("/") for row in sub.entries or []}
        assert sub_paths == {"skills/foo"}

    async def test_als_presents_virtual_keys_when_root_is_workspace_ancestor(
        self,
        tmp_path: Path,
    ) -> None:
        """``root_dir`` above the workspace: entries stay workspace-relative."""
        from deepagents.backends.local_shell import LocalShellBackend

        home = tmp_path / "home"
        workspace = home / ".octop" / "agents" / "MSPHTQ"
        workspace.mkdir(parents=True)
        backend = LocalShellBackend(root_dir=str(home), virtual_mode=True)
        ws = BackendWorkspace(backend, workspace)
        await ws.aupload_bytes("SOUL.md", b"# soul")
        await ws.aupload_bytes("agents/general.md", b"agent")

        result = await ws.als(".")
        assert result is not None
        paths = {row["path"].rstrip("/") for row in result.entries or []}
        assert paths == {"SOUL.md", "agents"}

        sub = await ws.als("agents")
        assert sub is not None
        sub_paths = {row["path"].rstrip("/") for row in sub.entries or []}
        assert sub_paths == {"agents/general.md"}


class TestSystemFilesPath:
    def test_persona_stays_at_workspace_root(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path, system_files_path=".octop")
        ws.write_text("AGENTS.md", "# agents", force=True)
        ws.write_text("skills/demo/SKILL.md", "# skill", force=True)
        ws.write_text(".bootstrapped", "", force=True)
        ws.write_text(".env", "A=1\n", force=True)
        assert (tmp_path / "AGENTS.md").is_file()
        assert (tmp_path / ".octop" / "skills" / "demo" / "SKILL.md").is_file()
        assert (tmp_path / ".octop" / ".bootstrapped").is_file()
        assert (tmp_path / ".octop" / ".env").is_file()
        assert not (tmp_path / "skills").exists()
        assert not (tmp_path / ".bootstrapped").exists()
        assert ws.exists("skills/demo/SKILL.md")
        assert ws.exists(".octop/skills/demo/SKILL.md")
        assert ws.read_text("AGENTS.md") == "# agents"

    def test_empty_prefix_keeps_legacy_layout(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path, system_files_path="")
        ws.write_text("skills/demo/SKILL.md", "# skill", force=True)
        assert (tmp_path / "skills" / "demo" / "SKILL.md").is_file()

    def test_does_not_double_prefix(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path, system_files_path=".octop")
        ws.write_text(".octop/skills/demo/SKILL.md", "# skill", force=True)
        assert (tmp_path / ".octop" / "skills" / "demo" / "SKILL.md").is_file()
        assert not (tmp_path / ".octop" / ".octop").exists()

    def test_reject_parent_escape(self) -> None:
        from octop_harness.backends.workspace import normalize_system_files_path

        with pytest.raises(ValueError, match="inside the workspace"):
            normalize_system_files_path("../oops")

    def test_reads_legacy_root_skills(self, fs_backend: Any, tmp_path: Path) -> None:
        legacy = tmp_path / "skills" / "legacy" / "SKILL.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("# legacy", encoding="utf-8")

        ws = BackendWorkspace(fs_backend, tmp_path, system_files_path=".octop")
        assert ws.exists("skills/legacy/SKILL.md")
        assert ws.read_text("skills/legacy/SKILL.md") == "# legacy"

    def test_canonical_skill_wins_on_read_collision(self, fs_backend: Any, tmp_path: Path) -> None:
        legacy = tmp_path / "skills" / "demo" / "SKILL.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("# legacy", encoding="utf-8")

        ws = BackendWorkspace(fs_backend, tmp_path, system_files_path=".octop")
        ws.write_text("skills/demo/SKILL.md", "# canonical", force=True)
        assert ws.read_text("skills/demo/SKILL.md") == "# canonical"

    def test_init_workspace_creates_system_files_root(self, fs_backend: Any, tmp_path: Path) -> None:
        ws = BackendWorkspace(fs_backend, tmp_path, system_files_path=".octop")
        ws.init_workspace(include_md_files=False, include_skills=False, include_agents=False)
        assert (tmp_path / ".octop").is_dir()
