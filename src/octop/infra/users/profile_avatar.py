"""Portraits for users and roles, stored as files under the Octop home."""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from pathlib import Path

from fastapi import Response

from octop.infra.agents.experts.avatar import sniff_avatar_media_type
from octop.infra.errors import ErrorCode, OctopError

_EXT_BY_MEDIA = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
_MEDIA_BY_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}
_STEM = re.compile(r"[A-Za-z0-9_-]{1,64}")
_ICON = re.compile(r"[a-z0-9-]{1,32}")


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


def _existing(directory: Path, stem: str) -> Path | None:
    for ext in _MEDIA_BY_EXT:
        path = directory / f"{stem}.{ext}"
        if path.is_file():
            return path
    return None


def profile_avatar_url(directory: Path, key: str, api_path: str) -> str | None:
    path = _existing(directory, _stem(key))
    if path is None:
        return None
    return f"{api_path}?v={int(path.stat().st_mtime)}"


def write_profile_avatar(directory: Path, key: str, data: bytes) -> None:
    media_type = sniff_avatar_media_type(data)
    stem = _stem(key)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{stem}.{_EXT_BY_MEDIA[media_type]}"
    # Stage the new portrait beside the current one and swap it in: deleting
    # first means a failed write leaves the user with no avatar at all. The
    # staging name is unique because a fixed ``<stem>.<ext>.tmp`` is shared by
    # concurrent uploads, and ``delete_profile_avatar``'s glob would remove
    # another request's staging file mid-write.
    fd, temp_name = tempfile.mkstemp(dir=directory, prefix=f".{stem}.", suffix=".tmp")
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        temporary.replace(destination)
    except BaseException:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise
    # ``_existing`` returns the first extension in ``_MEDIA_BY_EXT`` order, so
    # copies saved under another extension must go only after the swap.
    for path in directory.glob(f"{stem}.*"):
        if path.is_file() and path != destination:
            with contextlib.suppress(OSError):
                path.unlink()


def read_profile_avatar(directory: Path, key: str) -> tuple[bytes, str] | None:
    path = _existing(directory, _stem(key))
    if path is None:
        return None
    return path.read_bytes(), _MEDIA_BY_EXT[path.suffix.removeprefix(".").lower()]


def delete_profile_avatar(directory: Path, key: str) -> None:
    stem = _stem(key)
    if not directory.is_dir():
        return
    for path in directory.glob(f"{stem}.*"):
        if path.is_file():
            path.unlink()


def avatar_response(directory: Path, key: str) -> Response:
    found = read_profile_avatar(directory, key)
    if found is None:
        raise OctopError(ErrorCode.NOT_FOUND, "avatar not uploaded")
    data, media_type = found
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=60"},
    )
