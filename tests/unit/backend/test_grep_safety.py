"""Safe Python grep fallback (issue #2101)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from deepagents.backends.filesystem import FilesystemBackend

from octop.infra.backend.grep_safety import (
    _MAX_LINE_BYTES,
    install_safe_grep_fallback,
    is_virtual_fs_path,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="virtual-fs skip is POSIX-only")


def test_install_is_idempotent() -> None:
    install_safe_grep_fallback()
    first = FilesystemBackend._python_search
    install_safe_grep_fallback()
    assert FilesystemBackend._python_search is first
    assert getattr(FilesystemBackend._python_search, "__octop_safe_grep__", False)


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
    for rel in ("docker/Dockerfile",):
        text = (root / rel).read_text(encoding="utf-8")
        assert "ripgrep" in text, f"{rel} must install ripgrep"
