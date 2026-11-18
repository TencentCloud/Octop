"""Refuse mutating a storage backend still linked as the backup remote target."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from octop.config import load_config
from octop.infra.errors import ErrorCode, OctopError

BackupRemoteGuardAction = Literal["delete", "rename", "disable"]


def raise_if_backup_remote_backend(
    *,
    config_path: Path,
    backend_id: int,
    action: BackupRemoteGuardAction,
) -> None:
    """Raise ``STORAGE_BACKEND_REFERENCED`` when *backend_id* is the backup remote."""
    backup = load_config(config_path).backup
    if backup.remote_backend_id != backend_id:
        return
    verb = {
        "delete": "deleted",
        "rename": "renamed",
        "disable": "disabled",
    }[action]
    raise OctopError(
        ErrorCode.STORAGE_BACKEND_REFERENCED,
        f"storage backend id {backend_id} is the backup remote target and cannot be {verb}",
        details={
            "reason": "backup_remote",
            "action": action,
            "remote_backend_id": backend_id,
            "remote_enabled": backup.remote_enabled,
        },
    )
