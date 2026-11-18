"""Refuse mutating a storage backend still linked as the backup remote target."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from octop.config import load_config
from octop.infra.errors import ErrorCode, OctopError

BackupRemoteGuardAction = Literal["delete", "rename", "disable", "change_kind"]

_ACTION_LABELS = {
    "delete": "deleted",
    "rename": "renamed",
    "disable": "disabled",
    "change_kind": "changed",
}


def raise_if_backup_remote_backend(
    *,
    config_path: Path,
    backend_id: int,
    action: BackupRemoteGuardAction,
) -> None:
    """Raise ``STORAGE_BACKEND_BACKUP_REMOTE`` when *backend_id* is the backup remote."""
    backup = load_config(config_path).backup
    if backup.remote_backend_id != backend_id:
        return
    label = _ACTION_LABELS[action]
    raise OctopError(
        ErrorCode.STORAGE_BACKEND_BACKUP_REMOTE,
        f"storage backend id {backend_id} is the backup remote target and cannot be {label}",
        details={
            "action": label,
            "reason": "backup_remote",
            "remote_backend_id": backend_id,
            "remote_enabled": backup.remote_enabled,
        },
    )
