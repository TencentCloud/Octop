"""Orchestrate remote backup mirror / list / pull / prune."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from octop.infra.backup.remote.index import MirrorIndex, MirrorIndexEntry
from octop.infra.backup.remote.types import MirrorResult, RemoteBackupProvider, RemoteObject
from octop.infra.backup.store import (
    BackupContentFlags,
    backup_created_at_from_name,
    is_auto_backup_filename,
    is_backup_archive_filename,
    normalize_backup_filename,
    peek_backup_contents,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

# Sidecar next to each archive so cloud-first listing can show content flags
# without downloading the full ``.tar.gz`` (survives local cache wipes).
META_SUFFIX = ".octop-meta.json"


def meta_remote_name(archive_name: str) -> str:
    return f"{archive_name}{META_SUFFIX}"


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _flags_to_dict(flags: BackupContentFlags) -> dict[str, bool]:
    return {
        "includes_config": flags.includes_config,
        "includes_workspaces": flags.includes_workspaces,
        "includes_skill_packages": flags.includes_skill_packages,
        "includes_plugins": flags.includes_plugins,
        "includes_knowledge": flags.includes_knowledge,
        "includes_chats": flags.includes_chats,
    }


def _flags_from_dict(raw: dict[str, Any]) -> BackupContentFlags:
    return BackupContentFlags(
        includes_config=bool(raw.get("includes_config", True)),
        includes_workspaces=bool(raw.get("includes_workspaces", True)),
        includes_skill_packages=bool(raw.get("includes_skill_packages", True)),
        includes_plugins=bool(raw.get("includes_plugins", True)),
        includes_knowledge=bool(raw.get("includes_knowledge", True)),
        includes_chats=bool(raw.get("includes_chats", True)),
    )


class RemoteBackupEngine:
    """Mirror local archives through a ``RemoteBackupProvider``."""

    def __init__(
        self,
        *,
        paths: PathLayout,
        provider: RemoteBackupProvider,
        index: MirrorIndex | None = None,
    ) -> None:
        self._paths = paths
        self._provider = provider
        self._index = index or MirrorIndex.for_paths(paths)

    async def mirror(self, local_path: Path, remote_name: str | None = None) -> MirrorResult:
        name = normalize_backup_filename(remote_name or local_path.name)
        path = Path(local_path)
        if not path.is_file():
            result = MirrorResult(status="remote_failed", reason="local archive missing")
            self._record(name, result)
            return result
        digest = await asyncio.to_thread(sha256_file, path)
        result = await self._provider.put(path, name)
        result = MirrorResult(
            status=result.status,
            reason=result.reason,
            sha256=result.sha256 or digest,
        )
        self._record(name, result)
        if result.status == "remote_ok":
            await self._put_meta_sidecar(name, path)
        return result

    async def list_remote(self) -> list[RemoteObject]:
        return await self._provider.list()

    async def list_catalog(self) -> list[dict[str, Any]]:
        """Cloud-first backup rows (archives only), with content flags from meta/local."""
        objects = await self._provider.list()
        names = {o.name for o in objects}
        archives = [o for o in objects if is_backup_archive_filename(o.name)]
        archives.sort(key=lambda o: o.name, reverse=True)
        items: list[dict[str, Any]] = []
        for obj in archives:
            flags = await self._resolve_content_flags(obj.name, names)
            created = backup_created_at_from_name(obj.name, fallback_iso=obj.modified_at or None)
            modified = obj.modified_at or created
            payload: dict[str, Any] = {
                "name": obj.name,
                "size": obj.size,
                "modified_at": modified,
                "created_at": created,
                "includes_config": flags.includes_config,
                "includes_workspaces": flags.includes_workspaces,
                "includes_skill_packages": flags.includes_skill_packages,
                "includes_plugins": flags.includes_plugins,
                "includes_knowledge": flags.includes_knowledge,
                "includes_chats": flags.includes_chats,
                "remote_status": "remote_ok",
            }
            mirror = self._index.get(obj.name)
            if mirror is not None:
                payload["remote_status"] = mirror.status
                payload["remote_checked_at"] = mirror.checked_at
                if mirror.detail:
                    payload["remote_detail"] = mirror.detail
            items.append(payload)
        return items

    async def pull(self, remote_name: str) -> Path:
        name = normalize_backup_filename(remote_name)
        dest = self._paths.backups_dir / name
        if dest.exists():
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                f"local backup already exists: {name}",
            )
        return await self._download_to(name, dest)

    async def ensure_local(self, remote_name: str) -> Path:
        """Return local cache path, downloading from remote when missing."""
        name = normalize_backup_filename(remote_name)
        dest = self._paths.backups_dir / name
        if dest.is_file():
            return dest
        return await self._download_to(name, dest)

    async def delete_remote(self, remote_name: str) -> None:
        """Delete archive + meta sidecar on the remote (404 is fine)."""
        name = normalize_backup_filename(remote_name)
        await self._provider.delete(name)
        try:
            await self._provider.delete(meta_remote_name(name))
        except OctopError:
            logger.debug("remote meta delete skipped for %s", name, exc_info=True)

    async def prune_auto(self, *, keep: int, newest_status: str) -> list[str]:
        """Prune remote auto archives only after a verified newest mirror.

        ``newest_status`` must be ``remote_ok`` or this is a no-op.
        """
        if newest_status != "remote_ok":
            logger.info("skip remote prune: newest mirror status=%s", newest_status)
            return []
        if keep < 0:
            keep = 0
        objects = await self._provider.list()
        autos = [o for o in objects if is_auto_backup_filename(o.name)]
        # Prefer filename stamp (YYYYMMDDTHHMMSSZ) over WebDAV RFC1123 dates.
        autos.sort(key=lambda o: o.name, reverse=True)
        to_delete = autos[keep:]
        deleted: list[str] = []
        for obj in to_delete:
            try:
                await self.delete_remote(obj.name)
                deleted.append(obj.name)
            except Exception:
                logger.exception("failed to delete remote auto backup %s", obj.name)
        return deleted

    async def _download_to(self, name: str, dest: Path) -> Path:
        self._paths.backups_dir.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".pulling")
        try:
            await self._provider.get(name, tmp)
            if not tmp.is_file():
                raise OctopError(ErrorCode.NETWORK_ERROR, "remote pull produced no file")
            entry = self._index.get(name)
            size = tmp.stat().st_size
            if entry and entry.sha256:
                digest = await asyncio.to_thread(sha256_file, tmp)
                if digest != entry.sha256:
                    raise OctopError(
                        ErrorCode.NETWORK_ERROR,
                        "pulled archive sha256 does not match mirror index",
                    )
            # Always require a positive size; empty downloads are corrupt.
            if size <= 0:
                raise OctopError(ErrorCode.NETWORK_ERROR, "pulled archive is empty")
            tmp.replace(dest)
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise
        return dest

    async def _put_meta_sidecar(self, archive_name: str, local_archive: Path) -> None:
        flags = await asyncio.to_thread(peek_backup_contents, local_archive)
        payload = _flags_to_dict(flags)
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=META_SUFFIX,
                delete=False,
            ) as handle:
                json.dump(payload, handle)
                tmp_path = Path(handle.name)
            try:
                await self._provider.put(tmp_path, meta_remote_name(archive_name))
            finally:
                tmp_path.unlink(missing_ok=True)
        except Exception:
            logger.exception("failed to upload backup meta sidecar for %s", archive_name)

    async def _resolve_content_flags(
        self, archive_name: str, remote_names: set[str]
    ) -> BackupContentFlags:
        local = self._paths.backups_dir / archive_name
        if local.is_file():
            return await asyncio.to_thread(peek_backup_contents, local)
        meta_name = meta_remote_name(archive_name)
        if meta_name not in remote_names:
            return BackupContentFlags()
        return await self._fetch_meta_flags(meta_name)

    async def _fetch_meta_flags(self, meta_name: str) -> BackupContentFlags:
        fd, tmp_name = tempfile.mkstemp(suffix=META_SUFFIX)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            await self._provider.get(meta_name, tmp)
            raw = json.loads(tmp.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return _flags_from_dict(raw)
        except Exception:
            logger.debug("remote meta read failed for %s", meta_name, exc_info=True)
        finally:
            tmp.unlink(missing_ok=True)
        return BackupContentFlags()

    def _record(self, name: str, result: MirrorResult) -> None:
        self._index.set(
            name,
            MirrorIndexEntry(
                status=result.status,
                checked_at=_utc_now_iso(),
                detail=result.reason,
                sha256=result.sha256,
            ),
        )
