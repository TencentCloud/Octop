"""PostgreSQL mirror for one skill package's ``skills/`` tree.

The control-plane row stays in ``skill_packages``. File bytes live in
``public.skill_package_files``. Callers that still need a host directory
(local ``skills_dir`` mount, ZIP export) read a mirror rebuilt from that table.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from octop_harness.backends.cloud_storage_base import CloudStorageBackend
from octop_harness.backends.postgres import PostgresBackend


class SkillPackageBlobMirror:
    """Hydrate and persist ``{root}/{pack_id}/skills`` against PostgresBackend."""

    def __init__(self, backend: PostgresBackend, root: Path) -> None:
        self._backend = backend
        self._root = root

    def hydrate(self, pack_id: str) -> None:
        """Replace the local skills directory with the PostgreSQL copy."""
        dest_root = self._root / pack_id
        dest_root.mkdir(parents=True, exist_ok=True)
        staging = dest_root / ".skills-staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        prefix = f"/{pack_id}/skills"
        base = f"{prefix}/"
        collected = self._backend._collect_recursive(prefix)
        for virtual_path, file_data in collected.items():
            if not virtual_path.startswith(base):
                continue
            relative = virtual_path[len(base) :]
            if not relative:
                continue
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(CloudStorageBackend._file_data_to_bytes(file_data))
        marker_prefix = f"{pack_id}/skills/"
        for key in self._backend._iter_prefix_object_keys(prefix):
            text = str(key)
            if not text.endswith("/") or not text.startswith(marker_prefix):
                continue
            relative = text[len(marker_prefix) :].strip("/")
            if relative:
                (staging / relative).mkdir(parents=True, exist_ok=True)
        dest = dest_root / "skills"
        if dest.exists():
            shutil.rmtree(dest)
        staging.rename(dest)

    def persist(self, pack_id: str) -> None:
        """Replace the PostgreSQL tree with the local skills directory."""
        self.drop(pack_id)
        skills = self._root / pack_id / "skills"
        self._backend.mkdir_path(f"/{pack_id}/skills")
        if not skills.is_dir():
            return
        uploads: list[tuple[str, bytes]] = []
        for dirpath, _dirnames, filenames in os.walk(skills):
            current = Path(dirpath)
            relative_dir = current.relative_to(skills).as_posix()
            if relative_dir != ".":
                self._backend.mkdir_path(f"/{pack_id}/skills/{relative_dir}")
            for filename in filenames:
                path = current / filename
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                    payload = path.read_bytes()
                except OSError:
                    continue
                file_rel = path.relative_to(skills).as_posix()
                uploads.append((f"/{pack_id}/skills/{file_rel}", payload))
        if not uploads:
            return
        results = self._backend.upload_files(uploads)
        failed = [item for item in results if getattr(item, "error", None)]
        if failed:
            raise OSError(f"failed to store skill package files: {failed[0].error}")

    def drop(self, pack_id: str) -> None:
        self._backend.delete_prefix(f"/{pack_id}")
