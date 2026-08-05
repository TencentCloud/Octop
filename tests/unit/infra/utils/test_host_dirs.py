"""Tests for host directory listing helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from octop.infra.utils.host_dirs import (
    assert_safe_host_path,
    list_host_subdirs,
    mkdir_host_subdir,
    normalize_host_path,
    probe_host_root_dir,
    rename_host_dir,
)

# These tests assert POSIX path semantics (/proc, /etc, /root, "/" root, "~" home).
# The denied-prefix logic and "/" root probe are intentionally POSIX-only.
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX-only path semantics")


@posix_only
def test_normalize_host_path_expands_user_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert normalize_host_path("~") == tmp_path.resolve()


def test_list_host_subdirs_returns_child_directories(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")

    entries = list_host_subdirs(str(tmp_path))

    assert [item["name"] for item in entries] == ["alpha", "beta"]
    assert all(
        item["path"].endswith(name) for item, name in zip(entries, ["alpha", "beta"], strict=True)
    )


def test_list_host_subdirs_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a directory"):
        list_host_subdirs(str(tmp_path / "missing"))


@posix_only
def test_assert_safe_host_path_rejects_proc() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        assert_safe_host_path("/proc")


@posix_only
def test_assert_safe_host_path_rejects_etc() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        assert_safe_host_path("/etc/passwd")


@posix_only
def test_assert_safe_host_path_rejects_private_etc_symlink() -> None:
    """macOS resolves /etc → /private/etc; denial must still apply."""
    resolved = Path("/etc/passwd").resolve()
    if not str(resolved).startswith("/private/"):
        pytest.skip("host does not use /private/etc layout")
    with pytest.raises(ValueError, match="not allowed"):
        assert_safe_host_path(str(resolved))


@posix_only
def test_assert_safe_host_path_rejects_root() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        assert_safe_host_path("/root")


@posix_only
def test_probe_host_root_dir_skips_write_for_slash() -> None:
    result = probe_host_root_dir("/")
    assert result == {"ok": True, "path": "/"}


def test_probe_host_root_dir_ok(tmp_path: Path) -> None:
    result = probe_host_root_dir(str(tmp_path))
    assert result == {"ok": True, "path": str(tmp_path.resolve())}


def test_probe_host_root_dir_rejects_file(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("x", encoding="utf-8")
    result = probe_host_root_dir(str(file_path))
    assert result["ok"] is False
    assert result["code"] == "not_directory"


def test_mkdir_host_subdir_creates_unique_default_name(tmp_path: Path) -> None:
    created = mkdir_host_subdir(str(tmp_path), base_name="New Folder")
    assert created["name"] == "New Folder"
    assert (tmp_path / "New Folder").is_dir()
    assert Path(created["path"]).resolve() == (tmp_path / "New Folder").resolve()


def test_mkdir_host_subdir_increments_when_default_exists(tmp_path: Path) -> None:
    (tmp_path / "New Folder").mkdir()
    created = mkdir_host_subdir(str(tmp_path), base_name="New Folder")
    assert created["name"] == "New Folder (2)"
    assert (tmp_path / "New Folder (2)").is_dir()


def test_mkdir_host_subdir_rejects_invalid_base_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid name"):
        mkdir_host_subdir(str(tmp_path), base_name="../escape")


def test_rename_host_dir_renames_basename(tmp_path: Path) -> None:
    target = tmp_path / "New Folder"
    target.mkdir()
    renamed = rename_host_dir(str(target), "workspace")
    assert renamed["name"] == "workspace"
    assert not target.exists()
    assert (tmp_path / "workspace").is_dir()
    assert Path(renamed["path"]).resolve() == (tmp_path / "workspace").resolve()


def test_rename_host_dir_rejects_existing_name(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    with pytest.raises(ValueError, match="already exists"):
        rename_host_dir(str(tmp_path / "alpha"), "beta")


def test_rename_host_dir_rejects_path_separators(tmp_path: Path) -> None:
    target = tmp_path / "alpha"
    target.mkdir()
    with pytest.raises(ValueError, match="invalid name"):
        rename_host_dir(str(target), "nested/child")
