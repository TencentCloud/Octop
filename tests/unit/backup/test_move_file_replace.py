"""Cross-device backup moves fall back to copy."""

from __future__ import annotations

from pathlib import Path

from octop.infra.backup.store import move_file_replace


def test_move_file_replace_copies_when_rename_fails(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "tmp" / "backup.tar.gz"
    src.parent.mkdir()
    src.write_bytes(b"archive")
    dest = tmp_path / "other" / "backup.tar.gz"

    def _explode(self: Path, _target: Path) -> Path:
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(Path, "replace", _explode)

    move_file_replace(src, dest)

    assert dest.read_bytes() == b"archive"
    assert not src.exists()
