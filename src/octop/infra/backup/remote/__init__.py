"""Pluggable remote backup engine (WebDAV first; S3/Dropbox stubs)."""

from __future__ import annotations

# Register the WebDAV provider as a side effect of importing the package.
from octop.infra.backup.remote.providers import webdav as _webdav  # noqa: F401, E402
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
