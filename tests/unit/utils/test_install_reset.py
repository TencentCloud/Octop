"""Install-root wipe keeps the running virtualenv."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from octop.infra.utils.install_reset import (
    InstallResetError,
    partition_install_root,
    wipe_octop_state,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="symlink semantics")


def test_wipe_removes_state_and_keeps_named_runtime(tmp_path: Path) -> None:
    root = tmp_path / ".octop"
    (root / "agents").mkdir(parents=True)
    (root / "octop.db").write_text("db", encoding="utf-8")
    (root / "venv" / "bin").mkdir(parents=True)
    (root / "venv" / "bin" / "octop").write_text("x", encoding="utf-8")
    (root / "bin").mkdir()

    removed, kept = wipe_octop_state(root)
    assert {path.name for path in removed} == {"agents", "octop.db"}
    assert {path.name for path in kept} == {"bin", "venv"}
    assert (root / "venv" / "bin" / "octop").is_file()
    assert not (root / "agents").exists()


@posix_only
def test_wipe_unlinks_symlink_without_following(tmp_path: Path) -> None:
    root = tmp_path / ".octop"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("stay", encoding="utf-8")
    root.mkdir()
    (root / "link-out").symlink_to(outside)

    wipe_octop_state(root)
    assert not (root / "link-out").exists()
    assert (outside / "keep.txt").is_file()


def test_wipe_keeps_directory_that_holds_this_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".octop"
    custom = root / "custom-runtime"
    custom.mkdir(parents=True)
    (root / "octop.db").write_text("db", encoding="utf-8")
    monkeypatch.setattr("octop.infra.utils.install_reset.sys.prefix", str(custom))

    _removed, kept = wipe_octop_state(root)
    assert custom in kept
    assert not (root / "octop.db").exists()


def test_partition_refuses_when_root_is_the_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("octop.infra.utils.install_reset.sys.prefix", str(tmp_path))
    with pytest.raises(InstallResetError, match="install.sh"):
        partition_install_root(tmp_path)


def test_missing_root_is_empty(tmp_path: Path) -> None:
    assert partition_install_root(tmp_path / "missing") == ([], [])
