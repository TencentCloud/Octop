"""Resolve a ``RemoteBackupEngine`` from ``BackupConfig`` + storage backend row."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from octop.config import BackupConfig
from octop.infra.backup.remote.engine import RemoteBackupEngine
from octop.infra.backup.remote.index import MirrorIndex
from octop.infra.backup.remote.registry import get_provider
from octop.infra.backup.remote.types import BACKUP_REMOTE_KINDS, RemoteBackupProvider
from octop.infra.db.repos.backends import BackendRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

BackendGetter = Callable[[int], BackendRow | None]

# Fixed name for the Backup-page-managed WebDAV target row.
BACKUP_REMOTE_BACKEND_NAME = "octop-backup-remote"


def _parse_config_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def provider_kwargs_from_backend(row: BackendRow) -> dict[str, Any]:
    """Map a ``storage_backends`` row to provider factory kwargs."""
    kind = (row.kind or "").strip().lower()
    cfg = _parse_config_json(row.config_json)
    if kind == "webdav":
        return {
            "url": (row.endpoint or "").strip(),
            "username": row.access_key or "",
            "password": row.secret_key or "",
            "base_dir": str(cfg.get("base_dir") or ""),
            "verify_ssl": bool(cfg.get("verify_ssl", True)),
            "allow_insecure": bool(cfg.get("allow_insecure", False)),
        }
    # Future kinds can extend mapping here; stubs still receive the row fields.
    return {
        "endpoint": row.endpoint,
        "access_key": row.access_key,
        "secret_key": row.secret_key,
        "bucket": row.bucket,
        "region": row.region,
        "config": cfg,
    }


# Kinds that can actually mirror in this release (stubs stay in the registry).
_IMPLEMENTED_REMOTE_KINDS = frozenset({"webdav"})


def provider_from_backend(row: BackendRow) -> RemoteBackupProvider:
    kind = (row.kind or "").strip().lower()
    if kind not in BACKUP_REMOTE_KINDS:
        raise OctopError(
            ErrorCode.BACKUP_REMOTE_UNSUPPORTED,
            f"storage backend kind {kind!r} is not a remote backup target",
        )
    if kind not in _IMPLEMENTED_REMOTE_KINDS:
        raise OctopError(
            ErrorCode.BACKUP_REMOTE_UNSUPPORTED,
            f"remote backup kind {kind!r} is not implemented yet",
        )
    if not row.enabled:
        raise OctopError(
            ErrorCode.BACKUP_REMOTE_FAILED,
            f"remote backup storage backend {row.name!r} is disabled",
            details={"detail": f"backend {row.name!r} is disabled"},
        )
    return get_provider(kind, **provider_kwargs_from_backend(row))


def require_remote_backend(
    *,
    backup: BackupConfig,
    get_backend: BackendGetter,
) -> BackendRow:
    """Load the configured remote backend or fail closed when remote is enabled."""
    if not backup.remote_enabled:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "remote backup is not enabled",
        )
    backend_id = backup.remote_backend_id
    if backend_id is None:
        raise OctopError(
            ErrorCode.BACKUP_REMOTE_FAILED,
            "remote backup is enabled but remote_backend_id is not set",
            details={"detail": "remote_backend_id is not set"},
        )
    row = get_backend(backend_id)
    if row is None:
        raise OctopError(
            ErrorCode.BACKUP_REMOTE_FAILED,
            f"remote backup backend id {backend_id} not found",
            details={"detail": f"backend id {backend_id} not found"},
        )
    return row


def resolve_remote_engine(
    *,
    paths: PathLayout,
    backup: BackupConfig,
    get_backend: BackendGetter,
) -> RemoteBackupEngine | None:
    """Return an engine when remote mirroring is enabled; otherwise ``None``.

    Fail closed (raise) when enabled but the backend is missing, disabled, or
    not a supported remote-backup kind.
    """
    if not backup.remote_enabled:
        return None
    row = require_remote_backend(backup=backup, get_backend=get_backend)
    provider = provider_from_backend(row)
    return RemoteBackupEngine(paths=paths, provider=provider)


def redact_endpoint(endpoint: str | None) -> str | None:
    """Return a display URL without userinfo."""
    raw = (endpoint or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.username is not None or parsed.password is not None:
        # Should already be rejected at save time; never echo credentials.
        host = parsed.hostname or ""
        netloc = host
        if parsed.port:
            netloc = f"{host}:{parsed.port}"
        return parsed._replace(netloc=netloc).geturl()
    return raw


def remote_summary(
    *,
    paths: PathLayout,
    backup: BackupConfig,
    get_backend: BackendGetter,
) -> dict[str, Any]:
    """Payload fragment for Backup auto settings / Remote card."""
    summary: dict[str, Any] = {
        "remote_enabled": backup.remote_enabled,
        "remote_backend_id": backup.remote_backend_id,
        "kind": None,
        "endpoint": None,
        "base_dir": None,
        "backend_name": None,
        "last_mirror": None,
    }
    backend_id = backup.remote_backend_id
    if backend_id is None:
        return summary
    row = get_backend(backend_id)
    if row is None:
        summary["detail"] = "remote_backend_id references a missing storage backend"
        return summary
    cfg = _parse_config_json(row.config_json)
    summary.update(
        {
            "kind": (row.kind or "").lower() or None,
            "endpoint": redact_endpoint(row.endpoint),
            "base_dir": str(cfg.get("base_dir") or "") or None,
            "backend_name": row.name,
            "backend_enabled": bool(row.enabled),
        }
    )
    latest = MirrorIndex.for_paths(paths).latest()
    if latest is not None:
        name, entry = latest
        summary["last_mirror"] = {
            "name": name,
            **entry.to_dict(),
        }
    return summary


def webdav_config_json(
    *,
    base_dir: str = "",
    verify_ssl: bool = True,
    allow_insecure: bool = False,
) -> str:
    return json.dumps(
        {
            "base_dir": base_dir,
            "verify_ssl": verify_ssl,
            "allow_insecure": allow_insecure,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def raise_remote_mirror_failed(detail: str) -> None:
    """Raise ``BACKUP_REMOTE_FAILED`` with a redacted operator-facing detail."""
    text = (detail or "remote mirror failed").strip() or "remote mirror failed"
    raise OctopError(
        ErrorCode.BACKUP_REMOTE_FAILED,
        f"remote backup mirror failed: {text}",
        details={"detail": text},
    )
