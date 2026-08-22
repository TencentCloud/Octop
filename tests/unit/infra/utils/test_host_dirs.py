"""Tests for host directory listing helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from octop.infra.utils.host_dirs import (
    assert_safe_host_path,
    host_home_dir,
    is_within_host_home,
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
def test_assert_safe_host_path_rejects_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Deny /root only when it is not the process home (non-root Octop).
    home = tmp_path / "os_home"
    home.mkdir()
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: home)
    with pytest.raises(ValueError, match="not allowed"):
        assert_safe_host_path("/root")


@posix_only
def test_assert_safe_host_path_allows_root_when_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Octop running as uid 0 uses /root as home; default root_dir must probe OK."""
    root_home = Path("/root")
    if not root_home.is_dir():
        pytest.skip("/root not available")
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: root_home)
    assert assert_safe_host_path("/root") == root_home.resolve()
    nested = root_home / ".octop"
    # Nested path under home is allowed even if the parent is denylisted for others.
    assert assert_safe_host_path(str(nested)) == nested.resolve()


@posix_only
def test_list_host_subdirs_includes_root_home_when_denied_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process home ``/root`` must appear when listing ``/`` (uid 0 default)."""
    root_home = Path("/root")
    if not root_home.is_dir() or not os.access(root_home, os.R_OK | os.X_OK):
        pytest.skip("/root not readable")
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: root_home)

    entries = list_host_subdirs("/")
    paths = {item["path"] for item in entries}
    assert root_home.resolve().as_posix() in paths


@posix_only
def test_list_host_subdirs_hides_root_when_not_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "os_home"
    home.mkdir()
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: home)

    entries = list_host_subdirs("/")
    paths = {item["path"] for item in entries}
    assert "/root" not in paths


@posix_only
def test_probe_host_root_dir_skips_write_for_slash() -> None:
    result = probe_host_root_dir("/")
    assert result == {"ok": True, "path": "/"}


def test_probe_host_root_dir_ok(tmp_path: Path) -> None:
    result = probe_host_root_dir(str(tmp_path))
    assert result == {"ok": True, "path": tmp_path.resolve().as_posix()}


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


def test_is_within_host_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "os_home"
    home.mkdir()
    nested = home / "docs"
    nested.mkdir()
    outside = tmp_path / "other"
    outside.mkdir()
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: home)

    assert is_within_host_home(home.resolve())
    assert is_within_host_home(nested.resolve())
    assert not is_within_host_home(outside.resolve())
    assert host_home_dir() == home.resolve()


def test_assert_safe_host_path_restrict_to_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "os_home"
    home.mkdir()
    nested = home / "docs"
    nested.mkdir()
    outside = tmp_path / "other"
    outside.mkdir()
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: home)

    assert assert_safe_host_path(str(nested), restrict_to_home=True) == nested.resolve()
    with pytest.raises(ValueError, match="path outside home"):
        assert_safe_host_path(str(outside), restrict_to_home=True)
    with pytest.raises(ValueError, match="path outside home"):
        assert_safe_host_path("/", restrict_to_home=True)


def test_probe_host_root_dir_rejects_outside_home_when_restricted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "os_home"
    home.mkdir()
    outside = tmp_path / "other"
    outside.mkdir()
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: home)

    result = probe_host_root_dir(str(outside), restrict_to_home=True)
    assert result["ok"] is False
    assert result["code"] == "outside_home"

    ok = probe_host_root_dir(str(home), restrict_to_home=True)
    assert ok == {"ok": True, "path": home.resolve().as_posix()}


def test_host_fs_tree_root_admin_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.name != "posix":
        pytest.skip("POSIX tree root")
    home = Path("/tmp/octop-home-probe")
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: home)
    from octop.infra.utils.host_dirs import host_fs_tree_root

    assert host_fs_tree_root(allow_outside_home=True) == "/"
    assert host_fs_tree_root(allow_outside_home=False) == home.resolve().as_posix()


def test_list_and_probe_return_posix_paths(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    entries = list_host_subdirs(str(tmp_path))
    assert entries[0]["path"] == (tmp_path / "alpha").resolve().as_posix()
    probed = probe_host_root_dir(str(tmp_path))
    assert probed["path"] == tmp_path.resolve().as_posix()
