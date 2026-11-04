"""Published-expert snapshot trees stored in the control plane."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

from octop.infra.agents.experts.avatar import AVATAR_RELPATHS, LEGACY_AVATAR_RELPATHS
from octop.infra.agents.experts.catalog import MANIFEST_FILENAME
from octop.infra.db.repos.control_files import ControlFileRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.gateway.media.attachment_hints import sniff_image_media_type

_AVATAR_PATHS = AVATAR_RELPATHS + LEGACY_AVATAR_RELPATHS
_LOCAL_ADOPTED = "published_experts.local_adopted"


def persist_snapshot_dir(repo: ControlFileRepo, expert_id: str, directory: Path) -> None:
    """Replace the stored snapshot with the files under *directory*."""
    payloads: list[tuple[str, bytes]] = []
    if directory.is_dir():
        for dirpath, _dirnames, filenames in os.walk(directory):
            current = Path(dirpath)
            for filename in filenames:
                path = current / filename
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                    payload = path.read_bytes()
                except OSError:
                    continue
                payloads.append((path.relative_to(directory).as_posix(), payload))
    repo.replace_tree(ControlFileRepo.PUBLISHED_EXPERT, expert_id, payloads)


def materialize_snapshot(repo: ControlFileRepo, expert_id: str, dest: Path) -> bool:
    """Write the stored snapshot to *dest*. Return whether any file existed."""
    files = repo.list_files(ControlFileRepo.PUBLISHED_EXPERT, expert_id)
    if not files:
        return False
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for relative, content in files:
        target = dest.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return True


def read_snapshot_manifest(repo: ControlFileRepo, expert_id: str) -> dict[str, Any]:
    raw = repo.get(ControlFileRepo.PUBLISHED_EXPERT, expert_id, MANIFEST_FILENAME)
    if raw is None:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def read_published_avatar(repo: ControlFileRepo, expert_id: str) -> tuple[bytes, str] | None:
    for relative in _AVATAR_PATHS:
        data = repo.get(ControlFileRepo.PUBLISHED_EXPERT, expert_id, relative)
        if not data:
            continue
        media_type = sniff_image_media_type(data[:16]) or "application/octet-stream"
        return data, media_type
    return None


def published_skill_count(repo: ControlFileRepo, expert_id: str) -> int:
    """Count ``skills/<slug>/SKILL.md`` files in a stored snapshot."""
    count = 0
    for path in repo.paths(ControlFileRepo.PUBLISHED_EXPERT, expert_id):
        parts = path.split("/")
        if len(parts) == 3 and parts[0] == "skills" and parts[2] == "SKILL.md" and parts[1]:
            count += 1
    return count


def delete_snapshot(repo: ControlFileRepo, expert_id: str) -> None:
    repo.delete_owner(ControlFileRepo.PUBLISHED_EXPERT, expert_id)


def adopt_local_snapshots(repo: ControlFileRepo, settings: SettingsRepo, root: Path) -> None:
    """Copy snapshot directories once. A later disk copy cannot overwrite the database."""
    if settings.get(_LOCAL_ADOPTED) is not None:
        return
    if root.is_dir():
        for child in root.iterdir():
            if not child.is_dir() or child.name.startswith(".") or child.is_symlink():
                continue
            if repo.has_owner(ControlFileRepo.PUBLISHED_EXPERT, child.name):
                continue
            persist_snapshot_dir(repo, child.name, child)
    settings.set(_LOCAL_ADOPTED, "1")
