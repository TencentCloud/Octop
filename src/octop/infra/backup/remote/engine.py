"""Orchestrate remote backup mirror / list / pull / prune."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from octop.infra.backup.remote.index import MirrorIndex, MirrorIndexEntry
from octop.infra.backup.remote.types import MirrorResult, RemoteBackupProvider, RemoteObject
from octop.infra.backup.store import is_auto_backup_filename, normalize_backup_filename
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)


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
        digest = sha256_file(path)
        result = await self._provider.put(path, name)
        result = MirrorResult(
            status=result.status,
            reason=result.reason,
            sha256=result.sha256 or digest,
        )
        self._record(name, result)
        return result

    async def list_remote(self) -> list[RemoteObject]:
        return await self._provider.list()

    async def pull(self, remote_name: str) -> Path:
        name = normalize_backup_filename(remote_name)
        dest = self._paths.backups_dir / name
        if dest.exists():
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                f"local backup already exists: {name}",
            )
        self._paths.backups_dir.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".pulling")
        try:
            await self._provider.get(name, tmp)
            if not tmp.is_file():
                raise OctopError(ErrorCode.NETWORK_ERROR, "remote pull produced no file")
            entry = self._index.get(name)
            size = tmp.stat().st_size
            if entry and entry.sha256:
                digest = sha256_file(tmp)
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
        autos.sort(key=lambda o: o.modified_at or o.name, reverse=True)
        to_delete = autos[keep:]
        deleted: list[str] = []
        for obj in to_delete:
            try:
                await self._provider.delete(obj.name)
                deleted.append(obj.name)
            except Exception:
                logger.exception("failed to delete remote auto backup %s", obj.name)
        return deleted

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
