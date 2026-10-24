"""Grep runtime patches: bounded Python fallback (#2101) and ripgrep UTF-8 (#1959)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from deepagents.backends.filesystem import FilesystemBackend

from octop.infra.backend.grep_safety import (
    _MAX_LINE_BYTES,
    _command_is_ripgrep,
    _RipgrepSubprocess,
    install_safe_grep_fallback,
    is_virtual_fs_path,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="virtual-fs skip is POSIX-only")
posix_script = pytest.mark.skipif(
    os.name != "posix", reason="executable named rg is a POSIX script"
)


def test_install_is_idempotent() -> None:
    import deepagents.backends.filesystem as filesystem

    install_safe_grep_fallback()
    search = FilesystemBackend._python_search
    pipe = filesystem.subprocess
    install_safe_grep_fallback()
    assert FilesystemBackend._python_search is search
    assert filesystem.subprocess is pipe
    assert getattr(search, "__octop_safe_grep__", False)
    assert isinstance(pipe, _RipgrepSubprocess)
    assert subprocess.Popen is not pipe.Popen


def test_workspace_named_proc_is_still_searched(tmp_path: Path) -> None:
    install_safe_grep_fallback()
    nested = tmp_path / "proc"
    nested.mkdir()
    (nested / "note.txt").write_text("find-me\n", encoding="utf-8")
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=False)
    results, truncated, error = backend._python_search("find-me", tmp_path, None)
    assert truncated is False
    assert error is None
    texts = [text for matches in results.values() for _, text in matches]
    assert any("find-me" in text for text in texts)


@pytest.mark.parametrize("virtual_mode", [False, True])
@pytest.mark.parametrize("has_match", [False, True])
def test_single_file_does_not_walk_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, virtual_mode: bool, has_match: bool
) -> None:
    install_safe_grep_fallback()
    target = tmp_path / "target.txt"
    target.write_text("needle\n" if has_match else "hay\n", encoding="utf-8")
    (tmp_path / "sibling.txt").write_text("needle\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "other.txt").write_text("needle\n", encoding="utf-8")
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=virtual_mode)

    def no_walk(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("a single-file search must not traverse its parent")

    monkeypatch.setattr("octop.infra.backend.grep_safety.os.walk", no_walk)
    results, truncated, error = backend._python_search("needle", target, None)
    key = "/target.txt" if virtual_mode else str(target)
    assert results == ({key: [(1, "needle")]} if has_match else {})
    assert truncated is False
    assert error is None


@pytest.mark.parametrize("single_file", [False, True])
@pytest.mark.parametrize("include_glob", [None, "*.txt", "*.py"])
def test_file_and_directory_search_keep_glob_and_match_limit(
    tmp_path: Path, single_file: bool, include_glob: str | None
) -> None:
    install_safe_grep_fallback()
    nested = tmp_path / "nested"
    nested.mkdir()
    target = nested / "target.txt"
    target.write_text("needle one\nneedle two\n", encoding="utf-8")
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=False)
    results, truncated, error = backend._python_search(
        "needle", target if single_file else tmp_path, include_glob, max_count=1
    )
    matched = include_glob != "*.py"
    assert results == ({str(target): [(1, "needle one")]} if matched else {})
    assert truncated is matched
    assert error is None


@pytest.mark.parametrize("single_file", [False, True])
@pytest.mark.parametrize("limit", ["file", "line", "timeout"])
def test_file_and_directory_search_keep_safety_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, single_file: bool, limit: str
) -> None:
    install_safe_grep_fallback()
    target = tmp_path / "target.txt"
    target.write_text(
        "needle" + ("x" * (_MAX_LINE_BYTES + 1) if limit == "line" else ""),
        encoding="utf-8",
    )
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=False)
    if limit == "file":
        backend.max_file_size_bytes = 1
    if limit == "timeout":
        ticks = iter([0.0, 2.0, 2.0])
        monkeypatch.setattr("octop.infra.backend.grep_safety.time.monotonic", lambda: next(ticks))
    results, truncated, error = backend._python_search(
        "needle", target if single_file else tmp_path, None, timeout=1
    )
    assert results == {}
    assert truncated is (limit == "timeout")
    assert error is None


def test_oversized_line_is_skipped_without_match(tmp_path: Path) -> None:
    install_safe_grep_fallback()
    bomb = tmp_path / "bomb.bin"
    bomb.write_bytes(b"x" * (_MAX_LINE_BYTES + 64 * 1024))
    ok = tmp_path / "ok.txt"
    ok.write_text("needle in hay\n", encoding="utf-8")
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=False)
    results, truncated, error = backend._python_search("needle", tmp_path, None)
    assert truncated is False
    assert error is None
    assert any("needle" in text for matches in results.values() for _, text in matches)
    assert not any(str(bomb) in path or path.endswith("bomb.bin") for path in results)


@posix_only
def test_virtual_fs_path_prefixes() -> None:
    assert is_virtual_fs_path(Path("/proc"))
    assert is_virtual_fs_path(Path("/proc/1/pagemap"))
    assert is_virtual_fs_path(Path("/sys/kernel"))
    assert is_virtual_fs_path(Path("/dev/null"))
    assert not is_virtual_fs_path(Path("/etc/passwd"))
    assert not is_virtual_fs_path(Path("/root"))


@posix_only
def test_symlink_into_proc_is_skipped(tmp_path: Path) -> None:
    target = Path("/proc/1/pagemap")
    if not target.exists():
        pytest.skip("no /proc/1/pagemap")
    (tmp_path / "pagemap").symlink_to(target)
    (tmp_path / "ok.txt").write_text("needle\n", encoding="utf-8")
    install_safe_grep_fallback()
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=False)
    results, truncated, error = backend._python_search("needle", tmp_path, None)
    assert truncated is False
    assert error is None
    assert any("needle" in text for matches in results.values() for _, text in matches)
    assert not any(path.endswith("pagemap") for path in results)


@posix_only
@pytest.mark.skipif(not Path("/proc").is_dir(), reason="host has no /proc")
def test_python_search_does_not_walk_proc() -> None:
    install_safe_grep_fallback()
    backend = FilesystemBackend(root_dir="/", virtual_mode=False)
    results, truncated, error = backend._python_search(
        "octop-grep-safety-should-not-read-proc",
        Path("/proc"),
        None,
    )
    assert results == {}
    assert truncated is False
    assert error is None


def test_dockerfiles_install_ripgrep() -> None:
    root = Path(__file__).resolve().parents[3]
    for rel in ("docker/Dockerfile", "fnos/docker/Dockerfile"):
        text = (root / rel).read_text(encoding="utf-8")
        assert "ripgrep" in text, f"{rel} must install ripgrep"


def test_command_is_ripgrep() -> None:
    assert _command_is_ripgrep(["/usr/bin/rg", "--json"])
    assert _command_is_ripgrep(["C:\\Tools\\rg.exe", "--json"])
    assert _command_is_ripgrep((b"/opt/bin/rg",))
    assert not _command_is_ripgrep(["/usr/bin/python", "-c", "pass"])
    assert not _command_is_ripgrep("rg --json")
    assert not _command_is_ripgrep(b"rg")
    assert not _command_is_ripgrep([])
    assert not _command_is_ripgrep([object()])


def test_popen_forces_utf8_only_for_ripgrep() -> None:
    real = _RecordingSubprocess()
    proxy = _RipgrepSubprocess(real)
    proxy.Popen(["/usr/bin/rg", "--json"], stdout=subprocess.PIPE, text=True)
    proxy.Popen(
        ["C:\\ripgrep\\rg.EXE"],
        text=True,
        encoding="latin-1",
        errors="strict",
    )
    proxy.Popen([sys.executable, "-c", "pass"], text=True)
    proxy.Popen(["/usr/bin/rg"], stdout=subprocess.PIPE)

    rg_kwargs = real.calls[0][1]
    assert rg_kwargs["encoding"] == "utf-8"
    assert rg_kwargs["errors"] == "replace"
    explicit = real.calls[1][1]
    assert explicit["encoding"] == "latin-1"
    assert explicit["errors"] == "strict"
    assert "encoding" not in real.calls[2][1]
    assert "encoding" not in real.calls[3][1]
    assert proxy.PIPE == "pipe"


@posix_script
def test_installed_proxy_reads_utf8_that_is_illegal_in_gbk(tmp_path: Path) -> None:
    """Bytes that crash a cp936 decode must come back as text, not an exception."""
    install_safe_grep_fallback()
    import deepagents.backends.filesystem as filesystem

    rg = tmp_path / "rg"
    rg.write_text("#!/bin/sh\nprintf '%s' '中文'\n", encoding="utf-8")
    rg.chmod(0o755)
    proc = filesystem.subprocess.Popen(
        [os.fspath(rg)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, _stderr = proc.communicate(timeout=10)
    assert stdout == "中文"


@posix_script
def test_installed_proxy_replaces_invalid_utf8(tmp_path: Path) -> None:
    install_safe_grep_fallback()
    import deepagents.backends.filesystem as filesystem

    rg = tmp_path / "rg"
    rg.write_text("#!/bin/sh\nprintf '\\377\\376'\n", encoding="utf-8")
    rg.chmod(0o755)
    proc = filesystem.subprocess.Popen(
        [os.fspath(rg)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, _stderr = proc.communicate(timeout=10)
    assert stdout == "\ufffd\ufffd"


class _RecordingSubprocess:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def Popen(self, *args: Any, **kwargs: Any) -> str:
        self.calls.append((args, kwargs))
        return "proc"

    @property
    def PIPE(self) -> str:
        return "pipe"
