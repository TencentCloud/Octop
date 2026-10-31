"""Replacing a portrait must never drop the one already on disk."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.users.profile_avatar import read_profile_avatar, write_profile_avatar

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def _fail_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: Path, target: Path) -> None:
        raise OSError("no space left on device")

    monkeypatch.setattr(Path, "replace", boom)


def test_failed_swap_keeps_previous_avatar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "avatars"
    write_profile_avatar(directory, "7", PNG_BYTES)

    _fail_replace(monkeypatch)
    with pytest.raises(OSError):
        write_profile_avatar(directory, "7", JPEG_BYTES)

    found = read_profile_avatar(directory, "7")
    assert found is not None
    assert found == (PNG_BYTES, "image/png")


def test_failed_write_leaves_no_staging_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "avatars"
    write_profile_avatar(directory, "7", PNG_BYTES)

    _fail_replace(monkeypatch)
    with pytest.raises(OSError):
        write_profile_avatar(directory, "7", PNG_BYTES)

    assert sorted(p.name for p in directory.iterdir()) == ["7.png"]


def test_new_format_replaces_the_old_extension(tmp_path: Path) -> None:
    directory = tmp_path / "avatars"
    write_profile_avatar(directory, "7", PNG_BYTES)
    write_profile_avatar(directory, "7", JPEG_BYTES)

    assert sorted(p.name for p in directory.iterdir()) == ["7.jpg"]
    assert read_profile_avatar(directory, "7") == (JPEG_BYTES, "image/jpeg")
