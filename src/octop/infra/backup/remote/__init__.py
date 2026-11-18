"""Pluggable remote backup engine (WebDAV / COS / S3; Dropbox stub)."""

from __future__ import annotations

# Register providers as a side effect of importing the package.
from octop.infra.backup.remote.engine import RemoteBackupEngine
from octop.infra.backup.remote.providers import s3 as _s3  # noqa: F401, E402
from octop.infra.backup.remote.providers import webdav as _webdav  # noqa: F401, E402
from octop.infra.backup.remote.registry import get_provider, register_provider
from octop.infra.backup.remote.resolve import (
    BACKUP_REMOTE_BACKEND_NAME,
    provider_from_backend,
    remote_summary,
    resolve_remote_engine,
)
from octop.infra.backup.remote.types import (
    BACKUP_REMOTE_KINDS,
    MirrorResult,
    MirrorStatus,
    RemoteBackupProvider,
    RemoteObject,
)

__all__ = [
    "BACKUP_REMOTE_BACKEND_NAME",
    "BACKUP_REMOTE_KINDS",
    "MirrorResult",
    "MirrorStatus",
    "RemoteBackupEngine",
    "RemoteBackupProvider",
    "RemoteObject",
    "get_provider",
    "provider_from_backend",
    "register_provider",
    "remote_summary",
    "resolve_remote_engine",
]
