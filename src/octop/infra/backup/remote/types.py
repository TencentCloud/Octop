"""Types for the pluggable remote backup engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

MirrorStatus = Literal["remote_ok", "unverified", "remote_failed"]

# Kinds the remote backup engine knows about (stubs + WebDAV).
BACKUP_REMOTE_KINDS = frozenset({"webdav", "s3", "dropbox"})


@dataclass(frozen=True)
class MirrorResult:
    """Outcome of uploading one local archive to a remote provider."""

    status: MirrorStatus
    reason: str = ""
    sha256: str | None = None


@dataclass(frozen=True)
class RemoteObject:
    """One remote archive listing entry."""

    name: str
    size: int
    modified_at: str | None = None


class RemoteBackupProvider(Protocol):
    """Provider plugin for remote backup mirror/list/pull/delete/test."""

    async def test(self) -> None:
        """Raise if the remote endpoint is unreachable or misconfigured."""

    async def put(self, local_path: Path, remote_name: str) -> MirrorResult:
        """Upload ``local_path`` as ``remote_name`` and return verification status."""

    async def list(self) -> list[RemoteObject]:
        """List backup archives under the configured remote base directory."""

    async def get(self, remote_name: str, dest: Path) -> None:
        """Download ``remote_name`` into ``dest``."""

    async def delete(self, remote_name: str) -> None:
        """Delete ``remote_name`` from the remote base directory."""
