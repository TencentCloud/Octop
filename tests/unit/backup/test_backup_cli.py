"""Regression tests for `octop backup create --output` placement (#2321).

The CLI builds the archive inside a TemporaryDirectory() (one filesystem) and then
places it at ``--output`` (possibly a different filesystem). The original code used a
bare ``Path.replace``, which raises ``EXDEV`` (cross-device link) across filesystems
and then lost the archive to temp-dir cleanup. These tests cover the replacement
helper ``_atomic_move_to`` and its cross-device fallback ``_cross_device_copy``.
"""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from octop.cli.commands.backup import _atomic_move_to, _cross_device_copy


def _raise_exdev(src: Path, dest: Path) -> None:
    raise OSError(errno.EXDEV, "Cross-device link", str(src), None, str(dest))


def test_atomic_move_to_same_filesystem_moves_not_copies(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"hello")
    dest = tmp_path / "dest.bin"
    _atomic_move_to(src, dest)
    assert dest.read_bytes() == b"hello"
    assert not src.exists()  # moved, not copied
    assert dest.stat().st_size == 5


def test_atomic_move_to_creates_missing_parent_dirs(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    dest = tmp_path / "nested" / "deep" / "dest.bin"
    _atomic_move_to(src, dest)
    assert dest.read_bytes() == b"payload"
    assert not src.exists()


def test_atomic_move_to_overwrites_existing_dest(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"new-content")
    dest = tmp_path / "dest.bin"
    dest.write_bytes(b"old-content")
    _atomic_move_to(src, dest)
    assert dest.read_bytes() == b"new-content"


def test_atomic_move_to_cross_device_fallback(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    content = b"cross-device-archive-payload"
    src.write_bytes(content)
    dest = tmp_path / "dest.bin"
    # Force the EXDEV path even on a single filesystem.
    _atomic_move_to(src, dest, _replace=_raise_exdev)
    assert dest.read_bytes() == content
    # The staging file is consumed by the atomic swap; no .tmp leftovers remain.
    assert not any(p.name.startswith(".octop-backup-") for p in tmp_path.iterdir())
    assert dest.stat().st_size == len(content)


def test_atomic_move_to_keeps_existing_dest_when_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = tmp_path / "keep.bin"
    existing.write_bytes(b"pristine-backup")
    src = tmp_path / "src.bin"
    src.write_bytes(b"new")

    def _copy_fails(*_args, **_kwargs) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("octop.cli.commands.backup.shutil.copy2", _copy_fails)
    with pytest.raises(OSError):
        _atomic_move_to(src, existing, _replace=_raise_exdev)
    # A pre-existing destination is untouched on copy failure.
    assert existing.read_bytes() == b"pristine-backup"
    # The failed staging file is cleaned up.
    assert not any(p.name.startswith(".octop-backup-") for p in tmp_path.iterdir())


def test_atomic_move_to_propagates_non_exdev_errors(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"x")
    dest = tmp_path / "dest.bin"
    dest.write_bytes(b"original")

    def _raise_eacces(s: Path, d: Path) -> None:
        raise OSError(errno.EACCES, "Permission denied")

    with pytest.raises(OSError) as exc:
        _atomic_move_to(src, dest, _replace=_raise_eacces)
    assert exc.value.errno == errno.EACCES
    # A non-EXDEV failure must not touch the destination.
    assert dest.read_bytes() == b"original"


def test_cross_device_copy_writes_correct_bytes(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    content = b"".join(bytes([i % 256]) for i in range(4096))
    src.write_bytes(content)
    dest = tmp_path / "sub" / "dest.bin"
    _cross_device_copy(src, dest)
    assert dest.read_bytes() == content
    # Cross-device placement copies (the temp source is later removed by the
    # surrounding TemporaryDirectory), so the source still exists here.
    assert src.exists()
