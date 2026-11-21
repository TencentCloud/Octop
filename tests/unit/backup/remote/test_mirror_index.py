"""Mirror index persistence tests."""

from __future__ import annotations

from pathlib import Path

from octop.infra.backup.remote.index import MirrorIndex, MirrorIndexEntry


def test_mirror_index_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / ".remote-mirror.json"
    index = MirrorIndex(path)
    index.set(
        "octop-auto-backup-1.tar.gz",
        MirrorIndexEntry(
            status="remote_ok",
            checked_at="2026-01-01T00:00:00+00:00",
            detail="ok",
            sha256="abc",
        ),
    )
    loaded = MirrorIndex(path)
    entry = loaded.get("octop-auto-backup-1.tar.gz")
    assert entry is not None
    assert entry.status == "remote_ok"
    assert entry.sha256 == "abc"
