"""Expert avatars stored in the agent workspace via ``BackendWorkspace``."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from harness_agent.backends.utils import BackendOperationNotSupportedError

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.media.attachment_hints import sniff_image_media_type

MAX_AVATAR_BYTES = 5 * 1024 * 1024
AVATAR_DIR = ".octop"
_AVATAR_NAMES: tuple[str, ...] = (
    "avatar.png",
    "avatar.jpg",
    "avatar.jpeg",
    "avatar.webp",
    "avatar.gif",
)
AVATAR_RELPATHS: tuple[str, ...] = tuple(f"{AVATAR_DIR}/{name}" for name in _AVATAR_NAMES)
LEGACY_AVATAR_RELPATHS: tuple[str, ...] = _AVATAR_NAMES
_ALL_AVATAR_RELPATHS: tuple[str, ...] = AVATAR_RELPATHS + LEGACY_AVATAR_RELPATHS
_MEDIA_TO_RELPATH: dict[str, str] = {
    "image/png": f"{AVATAR_DIR}/avatar.png",
    "image/jpeg": f"{AVATAR_DIR}/avatar.jpg",
    "image/webp": f"{AVATAR_DIR}/avatar.webp",
    "image/gif": f"{AVATAR_DIR}/avatar.gif",
}


class WorkspaceAvatarIO(Protocol):
    async def aupload_bytes(self, path: str, data: bytes) -> None: ...

    async def adownload_bytes(self, path: str) -> bytes | None: ...

    async def adelete(self, path: str) -> None: ...


def agent_avatar_api_path(agent_id: str) -> str:
    return f"/api/agents/{agent_id}/avatar"


def published_expert_avatar_api_path(expert_id: str) -> str:
    return f"/api/experts/published/{expert_id}/avatar"


def display_agent_icon_url(
    *,
    agent_id: str,
    stored: str | None,
    updated_at: int | None = None,
) -> str | None:
    """Return the public ``icon_url``, cache-busting local workspace avatars."""
    text = str(stored or "").strip()
    if not text:
        return None
    local = agent_avatar_api_path(agent_id)
    if text.split("?", 1)[0] != local:
        return text
    version = int(updated_at or 0)
    if version <= 0:
        return local
    return f"{local}?v={version}"


def sniff_avatar_media_type(data: bytes) -> str:
    """Return a sniffed image media type or raise ``AVATAR_INVALID``."""
    if not data:
        raise OctopError(ErrorCode.AVATAR_INVALID, "avatar file is empty")
    if len(data) > MAX_AVATAR_BYTES:
        raise OctopError(ErrorCode.AVATAR_TOO_LARGE, "avatar exceeds 5 MiB")
    media_type = sniff_image_media_type(data)
    if media_type is None:
        raise OctopError(ErrorCode.AVATAR_INVALID, "avatar content is not a valid image")
    return media_type


def avatar_relpath_for_media(media_type: str) -> str:
    return _MEDIA_TO_RELPATH[media_type]


async def _download_avatar_bytes(workspace: WorkspaceAvatarIO, relpath: str) -> bytes | None:
    try:
        blob = await workspace.adownload_bytes(relpath)
    except (OSError, FileNotFoundError):
        return None
    return blob or None


async def write_workspace_avatar(workspace: WorkspaceAvatarIO, data: bytes) -> str:
    media_type = sniff_avatar_media_type(data)
    dest = avatar_relpath_for_media(media_type)
    await delete_workspace_avatar(workspace)
    amkdir = getattr(workspace, "amkdir", None)
    if callable(amkdir):
        with suppress(OSError, FileExistsError, BackendOperationNotSupportedError):
            await amkdir(AVATAR_DIR)
    await workspace.aupload_bytes(dest, data)
    return dest


async def read_workspace_avatar(workspace: WorkspaceAvatarIO) -> tuple[bytes, str] | None:
    for relpath in _ALL_AVATAR_RELPATHS:
        blob = await _download_avatar_bytes(workspace, relpath)
        if not blob:
            continue
        media_type = sniff_image_media_type(blob[:16]) or "application/octet-stream"
        return blob, media_type
    return None


async def delete_workspace_avatar(workspace: WorkspaceAvatarIO) -> None:
    for relpath in _ALL_AVATAR_RELPATHS:
        try:
            await workspace.adelete(relpath)
        except (OSError, FileNotFoundError):
            continue


async def copy_workspace_avatar_to_dir(workspace: WorkspaceAvatarIO, dest: Path) -> str | None:
    """Write the current avatar into a snapshot directory as ``.octop/avatar.*``."""
    found = await read_workspace_avatar(workspace)
    if found is None:
        return None
    data, media_type = found
    rel = avatar_relpath_for_media(media_type)
    target = dest.joinpath(*PurePosixPath(rel).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return rel


def read_snapshot_avatar(snapshot_dir: Path) -> tuple[bytes, str] | None:
    """Load ``.octop/avatar.*`` (or legacy root ``avatar.*``) from a published snapshot."""
    for relpath in _ALL_AVATAR_RELPATHS:
        path = snapshot_dir.joinpath(*PurePosixPath(relpath).parts)
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if not data:
            continue
        media_type = sniff_image_media_type(data[:16]) or "application/octet-stream"
        return data, media_type
    return None


def display_published_expert_icon_url(
    *,
    expert_id: str,
    snapshot_dir: Path,
    updated_at: str | int | None = None,
) -> str | None:
    """Public ``icon_url`` when the published snapshot contains an avatar file."""
    if read_snapshot_avatar(snapshot_dir) is None:
        return None
    local = published_expert_avatar_api_path(expert_id)
    version = str(updated_at or "").strip()
    if not version:
        return local
    return f"{local}?v={version}"


async def bind_workspace_avatar_icon_url(
    registry: Any,
    agent_id: str,
    workspace: WorkspaceAvatarIO,
) -> bool:
    """Point ``icon_url`` at the local avatar API when a workspace file exists."""
    if await read_workspace_avatar(workspace) is None:
        return False
    registry.set_icon_url(agent_id, agent_avatar_api_path(agent_id))
    return True
