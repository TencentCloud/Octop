"""Dropbox remote backup provider — not implemented in this phase."""

from __future__ import annotations

from pathlib import Path

from octop.infra.backup.remote.types import MirrorResult, RemoteObject
from octop.infra.errors import ErrorCode, OctopError


class DropboxBackupProvider:
    """Placeholder for a future OAuth Dropbox remote backup target."""

    async def test(self) -> None:
        raise OctopError(
            ErrorCode.BACKUP_REMOTE_UNSUPPORTED,
            "Dropbox remote backup provider is not implemented yet",
        )

    async def put(self, local_path: Path, remote_name: str) -> MirrorResult:
        raise OctopError(
            ErrorCode.BACKUP_REMOTE_UNSUPPORTED,
            "Dropbox remote backup provider is not implemented yet",
        )

    async def list(self) -> list[RemoteObject]:
        raise OctopError(
            ErrorCode.BACKUP_REMOTE_UNSUPPORTED,
            "Dropbox remote backup provider is not implemented yet",
        )

    async def get(self, remote_name: str, dest: Path) -> None:
        raise OctopError(
            ErrorCode.BACKUP_REMOTE_UNSUPPORTED,
            "Dropbox remote backup provider is not implemented yet",
        )

    async def delete(self, remote_name: str) -> None:
        raise OctopError(
            ErrorCode.BACKUP_REMOTE_UNSUPPORTED,
            "Dropbox remote backup provider is not implemented yet",
        )
