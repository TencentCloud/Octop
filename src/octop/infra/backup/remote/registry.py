"""Kind → remote backup provider factory."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from octop.infra.backup.remote.providers.dropbox import DropboxBackupProvider
from octop.infra.backup.remote.types import RemoteBackupProvider
from octop.infra.errors import ErrorCode, OctopError

ProviderFactory = Callable[..., RemoteBackupProvider]

_REGISTRY: dict[str, ProviderFactory] = {
    # ``webdav`` / ``s3`` / ``cos`` self-register on import.
    "dropbox": lambda **_kwargs: DropboxBackupProvider(),
}


def register_provider(kind: str, factory: ProviderFactory) -> None:
    """Register or replace a provider factory (used by tests and later plugins)."""
    key = kind.strip().lower()
    if not key:
        raise ValueError("remote backup kind must be non-empty")
    _REGISTRY[key] = factory


def get_provider(kind: str, **kwargs: Any) -> RemoteBackupProvider:
    """Return a provider instance for ``kind``.

    ``webdav`` / ``s3`` / ``cos`` self-register when their modules are
    imported; unknown kinds raise ``OctopError``.
    """
    key = (kind or "").strip().lower()
    factory = _REGISTRY.get(key)
    if factory is None:
        raise OctopError(
            ErrorCode.BACKUP_REMOTE_UNSUPPORTED,
            f"unsupported remote backup kind: {kind!r}",
        )
    return factory(**kwargs)
