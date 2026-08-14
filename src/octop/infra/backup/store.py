"""On-disk backup archive store under ``PathLayout.backups_dir``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

_BACKUP_SUFFIXES = (".tar.gz", ".tgz")
_BACKUP_CREATED_RE = re.compile(
    r"octop-(?:auto-)?backup-(\d{8}T\d{6}Z)",
)
_AUTO_BACKUP_PREFIX = "octop-auto-backup-"


def _iso_utc_from_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def resolve_backup_created_at(name: str, path: Path, *, mtime: float) -> str:
    """Filename stamp → birth time → mtime."""
    match = _BACKUP_CREATED_RE.search(name)
    if match:
        stamp = match.group(1)  # YYYYMMDDTHHMMSSZ
        try:
            parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            pass
        else:
            return parsed.isoformat()
    birth = getattr(path.stat(), "st_birthtime", None)
    if isinstance(birth, int | float) and birth > 0:
        return _iso_utc_from_timestamp(float(birth))
    return _iso_utc_from_timestamp(mtime)


@dataclass(frozen=True)
class BackupFileInfo:
    name: str
    size: int
    modified_at: str
    created_at: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "name": self.name,
            "size": self.size,
            "modified_at": self.modified_at,
            "created_at": self.created_at,
        }


def normalize_backup_filename(name: str) -> str:
    """Return a safe basename for a backup archive under ``backups_dir``."""
    base = Path(name).name.strip()
    if not base or base != name.strip() or "/" in base or "\\" in base:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid backup filename: {name!r}")
    if not any(base.endswith(suffix) for suffix in _BACKUP_SUFFIXES):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "backup file must end with .tar.gz or .tgz")
    return base


def list_backup_files(paths: PathLayout) -> list[BackupFileInfo]:
    root = paths.backups_dir
    if not root.is_dir():
        return []
    out: list[BackupFileInfo] = []
    for path in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        if not any(path.name.endswith(suffix) for suffix in _BACKUP_SUFFIXES):
            continue
        stat = path.stat()
        modified = _iso_utc_from_timestamp(stat.st_mtime)
        created = resolve_backup_created_at(path.name, path, mtime=stat.st_mtime)
        out.append(
            BackupFileInfo(
                name=path.name,
                size=stat.st_size,
                modified_at=modified,
                created_at=created,
            )
        )
    return out


def write_backup_file(paths: PathLayout, filename: str, data: bytes) -> BackupFileInfo:
    paths.ensure_backups_dir()
    safe = normalize_backup_filename(filename)
    dest = paths.backup_file(safe)
    dest.write_bytes(data)
    stat = dest.stat()
    modified = _iso_utc_from_timestamp(stat.st_mtime)
    created = resolve_backup_created_at(safe, dest, mtime=stat.st_mtime)
    return BackupFileInfo(
        name=safe,
        size=stat.st_size,
        modified_at=modified,
        created_at=created,
    )


def read_backup_file(paths: PathLayout, filename: str) -> bytes:
    safe = normalize_backup_filename(filename)
    path = paths.backup_file(safe)
    if not path.is_file():
        raise OctopError(ErrorCode.NOT_FOUND, f"backup not found: {safe}")
    return path.read_bytes()


def delete_backup_file(paths: PathLayout, filename: str) -> None:
    safe = normalize_backup_filename(filename)
    path = paths.backup_file(safe)
    if not path.is_file():
        raise OctopError(ErrorCode.NOT_FOUND, f"backup not found: {safe}")
    path.unlink()


def is_auto_backup_filename(name: str) -> bool:
    """True when ``name`` is an automatic backup archive (not a manual create)."""
    base = Path(name).name
    return base.startswith(_AUTO_BACKUP_PREFIX) and any(
        base.endswith(suffix) for suffix in _BACKUP_SUFFIXES
    )


def prune_auto_backups(paths: PathLayout, *, keep: int) -> list[str]:
    """Delete oldest automatic backups beyond ``keep``; return deleted filenames.

    Manual ``octop-backup-*`` archives are never removed. ``keep <= 0`` deletes
    all automatic backups.
    """
    autos = [f for f in list_backup_files(paths) if is_auto_backup_filename(f.name)]
    # list_backup_files is newest-first by mtime; prefer created_at stamp order.
    autos.sort(key=lambda f: f.created_at, reverse=True)
    if keep < 0:
        keep = 0
    to_delete = autos[keep:]
    deleted: list[str] = []
    for info in to_delete:
        try:
            delete_backup_file(paths, info.name)
        except OctopError:
            continue
        deleted.append(info.name)
    return deleted
