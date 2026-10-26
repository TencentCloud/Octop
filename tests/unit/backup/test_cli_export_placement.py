"""CLI backup export survives cross-filesystem EXDEV placement (#2321).

``octop backup create --output`` used to fail with ``OSError: [Errno 18]
Cross-device link`` when the output directory sits on another filesystem,
and the temp-dir cleanup then deleted the freshly built archive.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from octop.cli.commands.backup import _place_exported_archive


def test_same_filesystem_moves_atomically(tmp_path: Path) -> None:
    src = tmp_path / "backup.tar.gz"
    src.write_bytes(b"archive-bytes")
    dest = tmp_path / "out.tar.gz"

    _place_exported_archive(src, dest)

    assert dest.read_bytes() == b"archive-bytes"
    assert not src.exists()


def test_exdev_falls_back_to_staged_atomic_copy(tmp_path: Path, monkeypatch) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "backup.tar.gz"
    src.write_bytes(b"new-archive")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    dest = dest_dir / "out.tar.gz"
    dest.write_bytes(b"old-archive")

    real_replace = os.replace

    def failing_cross_device_replace(src_arg, dst_arg):
        # Simulate EXDEV for the staging-dir → dest move only; the staging
        # swap inside dest_dir stays on one filesystem and must succeed.
        if Path(src_arg) == src:
            raise OSError(errno.EXDEV, "Cross-device link")
        return real_replace(src_arg, dst_arg)

    monkeypatch.setattr(os, "replace", failing_cross_device_replace)

    _place_exported_archive(src, dest)

    assert dest.read_bytes() == b"new-archive"
    # No hidden .part staging leftovers next to the destination.
    assert [p.name for p in sorted(dest_dir.iterdir())] == ["out.tar.gz"]


def test_failed_copy_keeps_existing_destination(tmp_path: Path, monkeypatch) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "backup.tar.gz"
    src.write_bytes(b"new-archive")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    dest = dest_dir / "out.tar.gz"
    dest.write_bytes(b"old-archive")

    def exdev_replace(src_arg, dst_arg):
        raise OSError(errno.EXDEV, "Cross-device link")

    monkeypatch.setattr(os, "replace", exdev_replace)
    monkeypatch.setattr(
        "shutil.copyfile", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full"))
    )

    with pytest.raises(RuntimeError, match="disk full"):
        _place_exported_archive(src, dest)

    # The pre-existing backup stays intact and no staging file is leaked.
    assert dest.read_bytes() == b"old-archive"
    assert [p.name for p in sorted(dest_dir.iterdir())] == ["out.tar.gz"]


def test_unrelated_oserror_propagates_without_fallback(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "backup.tar.gz"
    src.write_bytes(b"archive")
    dest = tmp_path / "out.tar.gz"

    def denied_replace(src_arg, dst_arg):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(os, "replace", denied_replace)

    with pytest.raises(PermissionError):
        _place_exported_archive(src, dest)

    assert src.read_bytes() == b"archive"
    assert not dest.exists()
