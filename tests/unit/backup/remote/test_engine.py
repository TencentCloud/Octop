"""RemoteBackupEngine unit tests with a fake provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.backup.remote.engine import RemoteBackupEngine, sha256_file
from octop.infra.backup.remote.types import MirrorResult, RemoteObject
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout


class _FakeProvider:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_status: str = "remote_ok"
        self.deleted: list[str] = []

    async def test(self) -> None:
        return None

    async def put(self, local_path: Path, remote_name: str) -> MirrorResult:
        self.objects[remote_name] = local_path.read_bytes()
        return MirrorResult(status=self.put_status, reason="fake")  # type: ignore[arg-type]

    async def list(self) -> list[RemoteObject]:
        return [
            RemoteObject(name=name, size=len(blob), modified_at=name)
            for name, blob in self.objects.items()
        ]

    async def get(self, remote_name: str, dest: Path) -> None:
        blob = self.objects[remote_name]
        dest.write_bytes(blob)

    async def delete(self, remote_name: str) -> None:
        self.objects.pop(remote_name, None)
        self.deleted.append(remote_name)


@pytest.fixture
def layout(tmp_path: Path) -> PathLayout:
    root = tmp_path / "octop-home"
    root.mkdir()
    return PathLayout(root)


@pytest.mark.asyncio
async def test_mirror_records_sha256_and_status(layout: PathLayout) -> None:
    layout.backups_dir.mkdir(parents=True)
    local = layout.backups_dir / "octop-auto-backup-20260101T000000Z.tar.gz"
    local.write_bytes(b"hello-archive")
    provider = _FakeProvider()
    engine = RemoteBackupEngine(paths=layout, provider=provider)
    result = await engine.mirror(local)
    assert result.status == "remote_ok"
    assert result.sha256 == sha256_file(local)
    entry = engine._index.get(local.name)
    assert entry is not None
    assert entry.status == "remote_ok"
    assert entry.sha256 == result.sha256


@pytest.mark.asyncio
async def test_prune_auto_skipped_unless_remote_ok(layout: PathLayout) -> None:
    provider = _FakeProvider()
    for i in range(3):
        name = f"octop-auto-backup-2026010{i}T000000Z.tar.gz"
        provider.objects[name] = b"x" * (i + 1)
    engine = RemoteBackupEngine(paths=layout, provider=provider)
    deleted = await engine.prune_auto(keep=1, newest_status="unverified")
    assert deleted == []
    assert len(provider.objects) == 3


@pytest.mark.asyncio
async def test_prune_auto_keeps_retention_after_remote_ok(layout: PathLayout) -> None:
    provider = _FakeProvider()
    for i in range(3):
        name = f"octop-auto-backup-2026010{i}T000000Z.tar.gz"
        provider.objects[name] = b"x" * (i + 1)
    provider.objects["octop-backup-manual.tar.gz"] = b"manual"
    engine = RemoteBackupEngine(paths=layout, provider=provider)
    deleted = await engine.prune_auto(keep=1, newest_status="remote_ok")
    assert len(deleted) == 2
    assert "octop-backup-manual.tar.gz" in provider.objects
    assert len([n for n in provider.objects if n.startswith("octop-auto-backup-")]) == 1


@pytest.mark.asyncio
async def test_pull_rejects_existing_local(layout: PathLayout) -> None:
    layout.backups_dir.mkdir(parents=True)
    name = "octop-backup-20260101T000000Z.tar.gz"
    (layout.backups_dir / name).write_bytes(b"local")
    provider = _FakeProvider()
    provider.objects[name] = b"remote"
    engine = RemoteBackupEngine(paths=layout, provider=provider)
    with pytest.raises(OctopError) as exc_info:
        await engine.pull(name)
    assert exc_info.value.code == ErrorCode.SLASH_BAD_ARGS


@pytest.mark.asyncio
async def test_pull_writes_local_archive(layout: PathLayout) -> None:
    layout.backups_dir.mkdir(parents=True)
    name = "octop-backup-20260101T000000Z.tar.gz"
    provider = _FakeProvider()
    provider.objects[name] = b"remote-bytes"
    engine = RemoteBackupEngine(paths=layout, provider=provider)
    dest = await engine.pull(name)
    assert dest.read_bytes() == b"remote-bytes"
