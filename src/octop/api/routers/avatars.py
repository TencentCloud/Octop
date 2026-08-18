"""Avatar uploads for users and agents — ``~/.octop/avatars/``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, Response

from octop.api.deps import current_user, get_server
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

router = APIRouter()

MAX_AVATAR_BYTES = 5 * 1024 * 1024
ALLOWED_AVATAR_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def _paths(server: Any) -> PathLayout:
    paths: PathLayout = server.services.paths
    return paths


def _agent_config(row: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(row.config_json or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _require_avatar_target(
    kind: str,
    key: str,
    *,
    user: Any,
    server: Any,
    require_owner: bool,
) -> tuple[Path, PathLayout]:
    """Resolve and authorize the avatar file for ``kind`` ("users"|"agents").

    The users key may be a numeric id or ``me`` (the signed-in user).
    """
    if kind not in {"users", "agents"}:
        raise OctopError(ErrorCode.NOT_FOUND, f"unknown avatar kind {kind!r}")
    layout = _paths(server)
    if kind == "users":
        if key == "me":
            key = str(user.id)
        try:
            user_id = int(key)
        except ValueError as exc:
            raise OctopError(ErrorCode.NOT_FOUND, f"user {key!r} not found") from exc
        if server.services.user_repo.get(user_id) is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"user {key!r} not found")
        if require_owner and user_id != user.id:
            raise OctopError(ErrorCode.FORBIDDEN, "you can only manage your own avatar")
    else:
        repo = server.services.agent_repo
        row = repo.get(key)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"agent {key!r} not found")
        if require_owner and row.user_id is not None and row.user_id != user.id:
            raise OctopError(ErrorCode.FORBIDDEN, "you can only manage your own agents")
    return layout.avatar_file(kind, key), layout


@router.post("/{kind}/{key}", status_code=201, summary="Upload user/agent avatar")
async def upload_avatar(
    kind: Literal["users", "agents"],
    key: str,
    file: UploadFile = File(...),  # noqa: B008
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, str]:
    data = await file.read()
    if not data:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "avatar file is empty")
    if len(data) > MAX_AVATAR_BYTES:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "avatar exceeds 5 MiB")
    media_type = (file.content_type or "").split(";")[0].strip().lower()
    if media_type not in ALLOWED_AVATAR_TYPES:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "avatar must be PNG, JPEG, WebP, or GIF")
    # Magic-byte sniff so a renamed text file cannot masquerade as an image.
    if not looks_like_image(data):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "avatar content is not a valid image")

    target, layout = _require_avatar_target(kind, key, user=user, server=server, require_owner=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Write beside then replace — concurrent readers never see a partial file.
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(target)

    # Persist the reference so list/me projections can point at the file.
    if kind == "users":
        await server.user_manager.set_avatar_reference(user.id, layout.avatar_reference(kind, key))
    else:
        repo = server.services.agent_repo
        row = repo.get(key)
        cfg = _agent_config(row)
        cfg["avatar"] = layout.avatar_reference(kind, key)
        repo.update_config(key, config_json=json.dumps(cfg, ensure_ascii=False))

    return {
        "avatar_url": f"/api/avatars/{layout.avatar_reference(kind, key)}",
        "kind": kind,
        "key": key,
    }


@router.get("/{kind}/{key}", summary="Fetch user/agent avatar")
async def get_avatar(
    kind: str,
    key: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> FileResponse:
    # Read-only: any signed-in user may fetch (avatars appear in shared views).
    target, _layout = _require_avatar_target(
        kind, key, user=user, server=server, require_owner=False
    )
    if not target.is_file():
        raise OctopError(ErrorCode.NOT_FOUND, "avatar not uploaded")
    return FileResponse(
        target,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.delete("/{kind}/{key}", status_code=204, summary="Delete user/agent avatar")
async def delete_avatar(
    kind: Literal["users", "agents"],
    key: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Response:
    target, layout = _require_avatar_target(kind, key, user=user, server=server, require_owner=True)
    if target.is_file():
        target.unlink()

    # Clear the stored reference so UIs fall back to initials/icons.
    if kind == "users":
        await server.user_manager.set_avatar_reference(user.id, None)
    else:
        repo = server.services.agent_repo
        row = repo.get(key)
        if row is not None:
            cfg = _agent_config(row)
            cfg.pop("avatar", None)
            repo.update_config(key, config_json=json.dumps(cfg, ensure_ascii=False))
    return Response(status_code=204)


def looks_like_image(data: bytes) -> bool:
    """Magic-byte check for the allowed avatar image formats."""
    return (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        or data.startswith(b"\xff\xd8\xff")
        or (len(data) > 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP")
        or data.startswith((b"GIF87a", b"GIF89a"))
    )
