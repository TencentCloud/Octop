"""Tests for host directory listing helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from octop.infra.utils.host_dirs import (
    assert_safe_host_path,
    list_host_subdirs,
    normalize_host_path,
    probe_host_root_dir,
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
