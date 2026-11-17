"""Pluggable remote backup engine (WebDAV first; S3/Dropbox stubs)."""

from __future__ import annotations

from octop.infra.backup.remote.registry import get_provider, register_provider
from octop.infra.backup.remote.types import (
    BACKUP_REMOTE_KINDS,
    MirrorResult,
    MirrorStatus,
    RemoteBackupProvider,
    RemoteObject,
)

__all__ = [
    "BACKUP_REMOTE_KINDS",
    "MirrorResult",
    "MirrorStatus",
    "RemoteBackupProvider",
    "RemoteObject",
    "get_provider",
    "register_provider",
]
