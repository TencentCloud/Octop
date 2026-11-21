"""Portraits for users, roles, groups, and other control-plane records.

Bytes live in ``profile_avatars``. Callers pass an :class:`AvatarNamespace`
for one owner kind.
"""

from __future__ import annotations

import re

from fastapi import Response

from octop.infra.agents.experts.avatar import sniff_avatar_media_type
from octop.infra.db.repos.profile_avatars import ProfileAvatarRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

KIND_USER = "user"
KIND_ROLE = "role"
KIND_GROUP = "group"
KIND_SKILL_PACKAGE = "skill_package"
KIND_KNOWLEDGE_BASE = "knowledge_base"
KIND_BRIDGE = "bridge"

_ICON = re.compile(r"[a-z0-9-]{1,32}")
_STEM = re.compile(r"[A-Za-z0-9_-]{1,64}")
_LOCAL_ADOPTED = "profile_avatars.local_adopted"


def clean_avatar_icon(raw: str | None) -> str | None:
    """Return a preset icon id, or None for the built-in default."""
    if raw is None:
        return None
    value = raw.strip().lower()
    if not value:
        return None
    if not _ICON.fullmatch(value):
        raise OctopError(ErrorCode.AVATAR_INVALID, "avatar icon is invalid", status=400)
    return value


def _stem(key: str) -> str:
    stem = key.strip()
    if not _STEM.fullmatch(stem):
        raise OctopError(ErrorCode.AVATAR_INVALID, "avatar id is invalid", status=400)
    return stem


class AvatarNamespace:
    """Read and write portraits for one owner kind."""

    def __init__(self, repo: ProfileAvatarRepo, kind: str) -> None:
        self._repo = repo
        self.kind = kind

    def url(self, key: str, api_path: str) -> str | None:
        found = self._repo.get(self.kind, _stem(key))
        if found is None:
            return None
        return f"{api_path}?v={found.updated_at}"

    def write(self, key: str, data: bytes) -> None:
        media_type = sniff_avatar_media_type(data)
        self._repo.put(self.kind, _stem(key), data, media_type)

    def read(self, key: str) -> tuple[bytes, str] | None:
        found = self._repo.get(self.kind, _stem(key))
        if found is None:
            return None
        return found.content, found.media_type

    def delete(self, key: str) -> None:
        self._repo.delete(self.kind, _stem(key))

    def response(self, key: str) -> Response:
        found = self.read(key)
        if found is None:
            raise OctopError(ErrorCode.NOT_FOUND, "avatar not uploaded")
        data, media_type = found
        return Response(
            content=data,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=60"},
        )


def profile_avatar_url(store: AvatarNamespace, key: str, api_path: str) -> str | None:
    return store.url(key, api_path)


def write_profile_avatar(store: AvatarNamespace, key: str, data: bytes) -> None:
    store.write(key, data)


def read_profile_avatar(store: AvatarNamespace, key: str) -> tuple[bytes, str] | None:
    return store.read(key)


def delete_profile_avatar(store: AvatarNamespace, key: str) -> None:
    store.delete(key)


def avatar_response(store: AvatarNamespace, key: str) -> Response:
    return store.response(key)


def adopt_local_avatars(repo: ProfileAvatarRepo, settings: SettingsRepo, paths: PathLayout) -> None:
    """Copy leftover portrait files once. A row already stored is left alone."""
    if settings.get(_LOCAL_ADOPTED) is not None:
        return
    roots = {
        KIND_USER: paths.user_avatars_dir,
        KIND_ROLE: paths.role_avatars_dir,
        KIND_GROUP: paths.group_avatars_dir,
        KIND_SKILL_PACKAGE: paths.skill_package_avatars_dir,
        KIND_KNOWLEDGE_BASE: paths.knowledge_base_avatars_dir,
        KIND_BRIDGE: paths.bridge_avatars_dir,
    }
    for kind, directory in roots.items():
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if not path.is_file() or path.is_symlink():
                continue
            owner_id = path.stem
            if repo.get(kind, owner_id) is not None:
                continue
            try:
                payload = path.read_bytes()
                media_type = sniff_avatar_media_type(payload)
            except (OSError, OctopError):
                continue
            repo.put(kind, owner_id, payload, media_type)
    settings.set(_LOCAL_ADOPTED, "1")
