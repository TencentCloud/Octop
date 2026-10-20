"""Explicit virtual paths: file-tool chain, and no shell guessing."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import ExecuteResponse

from octop_harness.backends import _artifacts_root_for_workspace
from octop_harness.backends.explicit_virtual_path import (
    build_virtual_to_native_tool,
    resolve_explicit_virtual_path,
)
from octop_harness.backends.local_shell import HarnessLocalShellBackend


class _RecordingBackend:
    def __init__(self, inner: FilesystemBackend) -> None:
        self.inner = inner
        self.seen: list[str] = []

    def _resolve_path(self, key: str) -> Path:
        self.seen.append(key)
        return self.inner._resolve_path(key)


def test_native_drive_input_is_rejected_before_resolve(tmp_path: Path) -> None:
    root = tmp_path / "work"
    nested = root / "data" / "a.txt"
    nested.parent.mkdir(parents=True)
    nested.write_text("inside", encoding="utf-8")
    outside = tmp_path / "data" / "a.txt"
    outside.parent.mkdir()
    outside.write_text("outside", encoding="utf-8")
    backend = _RecordingBackend(FilesystemBackend(root_dir=str(root), virtual_mode=True))

    native = resolve_explicit_virtual_path("/data/a.txt", backend)
    assert Path(native) == nested.resolve()
    assert outside.read_text(encoding="utf-8") == "outside"
    assert backend.seen == ["/data/a.txt"]

    with pytest.raises(ValueError):
        resolve_explicit_virtual_path("C:/work/data/a.txt", backend)
    assert backend.seen == ["/data/a.txt"]


def test_resolve_receives_validate_path_result_not_the_original(tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    backend = _RecordingBackend(FilesystemBackend(root_dir=str(root), virtual_mode=True))
    native = resolve_explicit_virtual_path("/./data//a.txt", backend)
    assert backend.seen == ["/data/a.txt"]
    assert Path(native) == (root / "data" / "a.txt").resolve()


def test_missing_parents_map_under_the_root(tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    backend = FilesystemBackend(root_dir=str(root), virtual_mode=True)
    native = resolve_explicit_virtual_path("/new-parent/deep/new.txt", backend)
    assert Path(native) == (root / "new-parent" / "deep" / "new.txt").resolve()
    assert not Path(native).exists()


def test_traversal_fails_before_resolve(tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    backend = _RecordingBackend(FilesystemBackend(root_dir=str(root), virtual_mode=True))
    with pytest.raises(ValueError):
        resolve_explicit_virtual_path("/new-parent/../data/a.txt", backend)
    assert backend.seen == []


def test_tool_returns_a_typed_native_path(tmp_path: Path) -> None:
    root = tmp_path / "work"
    target = root / "data" / "a.txt"
    target.parent.mkdir(parents=True)
    target.write_text("inside", encoding="utf-8")
    tool = build_virtual_to_native_tool(FilesystemBackend(root_dir=str(root), virtual_mode=True))
    assert tool.name == "virtual_to_native_path"
    result = tool.func("/data/a.txt")
    assert result["kind"] == "native_path"
    assert Path(result["path"]) == target.resolve()
    with pytest.raises(ValueError):
        tool.func("C:/work/data/a.txt")


def test_explicit_execute_does_not_rewrite_command_env_or_output(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.txt").write_text("inside", encoding="utf-8")
    literal = f"C:\\work\\data\\a.txt and {tmp_path}{os.sep}data{os.sep}a.txt"
    backend = HarnessLocalShellBackend(
        root_dir=tmp_path,
        virtual_mode=True,
        explicit_virtual_paths=True,
        inherit_env=False,
        env={"FILE": "/data/a.txt"},
    )
    seen: dict[str, object] = {}

    def fake_execute(command: str, *, timeout: int | None = None) -> ExecuteResponse:
        del timeout
        seen["command"] = command
        seen["env"] = dict(backend._env)
        return ExecuteResponse(output=literal, exit_code=0, truncated=False)

    backend._execute_on_host = fake_execute  # type: ignore[method-assign]
    response = backend.execute("type /data/a.txt")
    assert seen["command"] == "type /data/a.txt"
    assert seen["env"] == {"FILE": "/data/a.txt"}
    assert response.output == literal


def test_explicit_flag_skips_same_drive_artifacts_shortcut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = (tmp_path / "host-root").resolve()
    workspace = host / "agents" / "id"
    workspace.mkdir(parents=True)
    original = Path.resolve

    def fake_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        raw = os.fspath(self)
        # POSIX pathlib drops the slash in ``C:/``, so the path object is ``C:``.
        if raw in {"/", "C:", "C:/", "C:\\"}:
            return host
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    plain = _artifacts_root_for_workspace(workspace, root_dir="C:/", system_files_path=".octop")
    flagged = _artifacts_root_for_workspace(
        workspace,
        root_dir="C:/",
        system_files_path=".octop",
        explicit_virtual_paths=True,
    )
    assert plain == str((workspace / ".octop").resolve())
    assert flagged == "/agents/id/.octop"
