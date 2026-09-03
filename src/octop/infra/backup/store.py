"""On-disk backup archive store under ``PathLayout.backups_dir``."""

from __future__ import annotations

import json
import re
import shutil
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from octop.infra.backup.manifest import BackupManifest
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
    includes_config: bool = True
    includes_workspaces: bool = True
    includes_skill_packages: bool = True
    includes_plugins: bool = True
    includes_knowledge: bool = True
    includes_chats: bool = True

    def to_dict(self) -> dict[str, str | int | bool]:
        return {
            "name": self.name,
            "size": self.size,
            "modified_at": self.modified_at,
            "created_at": self.created_at,
            "includes_config": self.includes_config,
            "includes_workspaces": self.includes_workspaces,
            "includes_skill_packages": self.includes_skill_packages,
            "includes_plugins": self.includes_plugins,
            "includes_knowledge": self.includes_knowledge,
            "includes_chats": self.includes_chats,
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
        out.append(backup_file_info(path))
    return out


def backup_file_info(path: Path) -> BackupFileInfo:
    """Build ``BackupFileInfo`` from an existing archive path."""
    path = Path(path)
    if not path.is_file():
        raise OctopError(ErrorCode.NOT_FOUND, f"backup not found: {path.name}")
    stat = path.stat()
    modified = _iso_utc_from_timestamp(stat.st_mtime)
    created = resolve_backup_created_at(path.name, path, mtime=stat.st_mtime)
    contents = peek_backup_contents(path)
    return BackupFileInfo(
        name=path.name,
        size=stat.st_size,
        modified_at=modified,
        created_at=created,
        includes_config=contents.includes_config,
        includes_workspaces=contents.includes_workspaces,
        includes_skill_packages=contents.includes_skill_packages,
        includes_plugins=contents.includes_plugins,
        includes_knowledge=contents.includes_knowledge,
        includes_chats=contents.includes_chats,
    )


@dataclass(frozen=True)
class BackupContentFlags:
    includes_config: bool = True
    includes_workspaces: bool = True
    includes_skill_packages: bool = True
    includes_plugins: bool = True
    includes_knowledge: bool = True
    includes_chats: bool = True


_FULL_CONTENTS = BackupContentFlags()


def peek_backup_contents(path: Path) -> BackupContentFlags:
    """Read ``manifest.json`` from an archive.

    Unreadable archives default to all-included. Legacy archives that omit
    ``includes_plugins`` / ``includes_knowledge`` keep those live directories
    on restore.
    """
    try:
        with tarfile.open(path, mode="r:*") as tf:
            member = tf.extractfile("manifest.json")
            if member is None:
                return _FULL_CONTENTS
            raw: Any = json.loads(member.read().decode("utf-8"))
        if not isinstance(raw, dict):
            return _FULL_CONTENTS
        manifest = BackupManifest.from_dict(raw)
    except (
        OSError,
        tarfile.TarError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        ValueError,
        TypeError,
    ):
        return _FULL_CONTENTS
    return BackupContentFlags(
        includes_config=bool(manifest.includes_config or manifest.includes_env),
        includes_workspaces=any(entry.workspace_included for entry in manifest.agents),
        includes_skill_packages=bool(manifest.includes_skill_packages),
        includes_plugins=bool(manifest.includes_plugins),
        includes_knowledge=bool(manifest.includes_knowledge),
        includes_chats=bool(manifest.includes_chats),
    )


def write_backup_file(paths: PathLayout, filename: str, data: bytes) -> BackupFileInfo:
    paths.ensure_backups_dir()
    safe = normalize_backup_filename(filename)
    dest = paths.backup_file(safe)
    dest.write_bytes(data)
    return backup_file_info(dest)


def place_backup_file(paths: PathLayout, filename: str, src: Path) -> BackupFileInfo:
    """Move *src* into ``backups_dir`` under *filename* (atomic replace when possible)."""
    paths.ensure_backups_dir()
    safe = normalize_backup_filename(filename)
    dest = paths.backup_file(safe)
    src = Path(src)
    if src.resolve() == dest.resolve():
        return backup_file_info(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        src.replace(dest)
    except OSError:
        shutil.copy2(src, dest)
        src.unlink(missing_ok=True)
    return backup_file_info(dest)


def resolve_backup_path(paths: PathLayout, filename: str) -> Path:
    """Return the on-disk path for a stored backup (must exist)."""
    safe = normalize_backup_filename(filename)
    path = paths.backup_file(safe)
    if not path.is_file():
        raise OctopError(ErrorCode.NOT_FOUND, f"backup not found: {safe}")
    return path


def read_backup_file(paths: PathLayout, filename: str) -> bytes:
    return resolve_backup_path(paths, filename).read_bytes()


def delete_backup_file(paths: PathLayout, filename: str) -> None:
    path = resolve_backup_path(paths, filename)
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
