"""Refuse mutating a storage backend still linked as the backup remote target."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from octop.config import load_config
from octop.infra.backup.auto import update_server_backup_config
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
    """Raise when *backend_id* is occupied as the active backup destination.

    Delete is blocked only while ``remote_enabled`` (actively selected). A
    dangling ``remote_backend_id`` with remote disabled is not "occupied".
    Rename / disable / change-kind stay blocked whenever the id is linked.
    """
    backup = load_config(config_path).backup
    if backup.remote_backend_id != backend_id:
        return
    if action == "delete" and not backup.remote_enabled:
        return
    label = _ACTION_LABELS[action]
    raise OctopError(
        ErrorCode.STORAGE_BACKEND_BACKUP_REMOTE,
        f"storage backend id {backend_id} is the backup remote target and cannot be {label}",
        details={
            "action": label,
            "remote_backend_id": backend_id,
            "remote_enabled": backup.remote_enabled,
        },
    )


def unlink_backup_remote_backend(
    *,
    server: Any,
    backend_id: int,
) -> bool:
    """Clear a dangling backup remote link (remote not enabled).

    Returns True when a link was cleared. No-op when the backend is not linked
    or when remote is still enabled (caller must refuse delete first).
    """
    config = load_config(server.paths.config)
    backup = config.backup
    if backup.remote_backend_id != backend_id:
        return False
    if backup.remote_enabled:
        return False
    cleared = replace(backup, remote_enabled=False, remote_backend_id=None)
    update_server_backup_config(server, cleared)
    return True
