"""On-disk mirror status index under ``backups_dir/.remote-mirror.json``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from octop.infra.backup.remote.types import MirrorStatus
from octop.infra.errors import corrupt_config_error
from octop.infra.utils.json_file import (
    JsonFileCorruptError,
    read_json_object,
    write_json_atomic,
)
from octop.infra.utils.paths import PathLayout

INDEX_FILENAME = ".remote-mirror.json"


@dataclass
class MirrorIndexEntry:
    status: MirrorStatus
    checked_at: str
    detail: str = ""
    sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checked_at": self.checked_at,
            "detail": self.detail,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> MirrorIndexEntry:
        status = str(raw.get("status") or "remote_failed")
        if status not in {"remote_ok", "unverified", "remote_failed"}:
            status = "remote_failed"
        sha = raw.get("sha256")
        return cls(
            status=status,  # type: ignore[arg-type]
            checked_at=str(raw.get("checked_at") or ""),
            detail=str(raw.get("detail") or ""),
            sha256=str(sha) if sha else None,
        )


class MirrorIndex:
    """JSON map of backup filename → mirror status."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: dict[str, MirrorIndexEntry] = {}
        self._load()

    @classmethod
    def for_paths(cls, paths: PathLayout) -> MirrorIndex:
        return cls(paths.backups_dir / INDEX_FILENAME)

    def _load(self) -> None:
        try:
            raw = read_json_object(self._path)
        except JsonFileCorruptError as exc:
            raise corrupt_config_error(exc.path, exc.detail) from exc
        if raw is None:
            self._entries = {}
            return
        entries: dict[str, MirrorIndexEntry] = {}
        for name, value in raw.items():
            if isinstance(value, dict):
                entries[str(name)] = MirrorIndexEntry.from_dict(value)
        self._entries = entries

    def get(self, name: str) -> MirrorIndexEntry | None:
        return self._entries.get(name)

    def set(self, name: str, entry: MirrorIndexEntry) -> None:
        prior = self._entries.get(name)
        if entry.sha256 is None and prior is not None and prior.sha256:
            entry = MirrorIndexEntry(
                status=entry.status,
                checked_at=entry.checked_at,
                detail=entry.detail,
                sha256=prior.sha256,
            )
        self._entries[name] = entry
        self._save()

    def _save(self) -> None:
        payload = {name: entry.to_dict() for name, entry in sorted(self._entries.items())}
        write_json_atomic(self._path, payload)
