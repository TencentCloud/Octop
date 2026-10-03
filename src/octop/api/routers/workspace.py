"""Workspace router — read/write into a running agent's workspace."""

from __future__ import annotations

import logging
import posixpath
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from octop_harness.backends.utils import BackendOperationNotSupportedError
from pydantic import BaseModel

from octop.api.common.agent_workspace import resolve_agent_workspace_dir
from octop.api.common.content_disposition import content_disposition
from octop.api.common.workspace import (
    coerce_read_content,
    file_info_to_dict,
    reanchor_entry_path,
    require_agent_workspace,
    require_running_workspace,
    workspace_api_path,
)
from octop.api.deps import current_user, get_server
from octop.infra.agents.builtin_skills import is_octop_builtin_skills_path
from octop.infra.backup.workspace_archive import export_workspace_zip, import_workspace_zip
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.media.backend_files import (
    backend_workspace_path,
    is_allowed_host_download_abs_path,
    is_host_absolute_path,
    resolve_preview_payload,
)
from octop.infra.utils.doc_edit import DocConverter, get_doc_converter

logger = logging.getLogger(__name__)

_PROTECTED_PREFIX = "_builtin_skills"


def _workspace_key(rel: str, *, workspace: Any) -> str:
    """Fold *rel* to the workspace-relative key ``BackendWorkspace`` will resolve.

    Host-absolute spellings that land inside the workspace fold to the same key a
    relative request produces, so ``/w/sub/../_builtin_skills/x`` and
    ``_builtin_skills/x`` are judged identically instead of by how they are spelled.
    """
    posix = posixpath.normpath(rel.strip().replace("\\", "/"))
    root = str(Path(workspace.workspace_dir).expanduser().resolve()).replace("\\", "/")
    if posix == root:
        return "."
    for prefix in (f"{root}/", "/"):
        if posix.startswith(prefix):
            return posix[len(prefix) :]
    return posix


def _api_workspace_path(rel: str, *, fallback: str) -> str:
    """Echo the workspace path in the ``/…`` form the API and dashboard use.

    The guard may have folded the request into a host path, so the raw request is
    only a fallback — it can name a different file than the one written.
    """
    key = posixpath.normpath(rel.strip().replace("\\", "/"))
    if key in ("", "."):
        return fallback
    return key if key.startswith("/") else f"/{key}"


def _assert_inside_workspace(rel: str, *, workspace: Any, original: str) -> None:
    """Reject a resolved mutation target that lands outside the agent workspace.

    ``_workspace_io_path`` returns a host absolute path for ``file://`` URLs and
    (with ``from_workspace=false``) for a leading ``/`` or ``~``. Those never
    reach ``BackendWorkspace``'s own containment check, which only guards keys
    *without* a leading slash, so the caller has to vet them here.

    Sandbox backends (``sandbox_fs``) are exempt: agent content lives inside the
    sandbox, so a host-absolute spelling resolves to a container path rather than
    the host filesystem — while that same spelling *is* the legitimate workspace
    key the dashboard sends (``file:///workspace/x.md``).
    """
    if getattr(getattr(workspace, "backend", None), "sandbox_fs", False):
        return
    raw = rel.strip().replace("\\", "/")
    if not raw.startswith("~") and not is_host_absolute_path(raw):
        # Workspace-relative keys are resolved against the workspace by the
        # backend, which applies its own containment check.
        return
    if raw.startswith("~") and not raw.startswith("~/"):
        # ``~notes.md`` names a workspace file, not a home dir. ``expanduser``
        # leaves it alone, so the backend would resolve it against the process
        # cwd — refuse rather than write somewhere unrelated to the request.
        raise OctopError(
            ErrorCode.FORBIDDEN,
            f"cannot modify {original!r}: '~' paths must be '~/…'",
        )
    # Containment is decided lexically. ``resolve()`` on the request value is a
    # filesystem touch of attacker-controlled data — CodeQL reads it as a
    # path-injection sink, and no inline suppression clears it — while
    # ``normpath`` folds ``..`` just as well for deciding whether the target is
    # inside the workspace. Symlink escape is left to the backend, which
    # resolves and re-checks every relative key it is handed.
    #
    # Both spellings of the root are compared: ``resolve()`` may add or drop a
    # symlinked ancestor (``/tmp`` → ``/private/tmp`` on macOS) and the request
    # may legitimately spell the path either way.
    configured = Path(workspace.workspace_dir).expanduser()
    roots = {
        posixpath.normpath(str(configured.resolve())),
        posixpath.normpath(str(configured)),
    }
    candidate = posixpath.normpath(raw)
    for root in roots:
        if candidate == root or candidate.startswith(f"{root}/"):
            return
    raise OctopError(
        ErrorCode.FORBIDDEN,
        f"cannot modify {original!r}: path is outside the agent workspace",
    )


def _assert_workspace_mutable(
    path: str,
    *,
    workspace: Any,
    from_workspace: bool = True,
) -> str:
    """Vet a mutation target and return the path the caller must write to.

    Mutations address the agent workspace, so the resolved target has to stay
    inside it — a ``file://`` URL or a host-absolute ``/…`` that points anywhere
    else is refused. The returned path is the one to hand to the backend, so the
    check and the write can never disagree; callers reporting a path to the client
    go through :func:`_api_workspace_path` rather than echoing the raw request.
    """
    rel = _workspace_io_path(path, from_workspace=from_workspace)
    # Folded to the key the backend resolves, then matched by the same predicate
    # archive import/export uses, so "owned by Octop" is decided in one place.
    key = _workspace_key(rel, workspace=workspace)
    if key == ".":
        raise OctopError(ErrorCode.FORBIDDEN, "cannot modify workspace root")
    if is_octop_builtin_skills_path(key):
        raise OctopError(ErrorCode.FORBIDDEN, f"cannot modify {_PROTECTED_PREFIX!r} paths")
    _assert_inside_workspace(rel, workspace=workspace, original=path)
    return rel


def _map_workspace_fs_error(exc: Exception, *, operation: str, path: str) -> OctopError:
    if isinstance(exc, BackendOperationNotSupportedError):
        return OctopError(ErrorCode.WORKSPACE_OP_UNSUPPORTED, str(exc))
    if isinstance(exc, FileNotFoundError):
        return OctopError(ErrorCode.NOT_FOUND, f"cannot {operation} {path!r}: not found")
    if isinstance(exc, FileExistsError):
        return OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc))
    if isinstance(exc, PermissionError):
        return OctopError(ErrorCode.FORBIDDEN, str(exc))
    if isinstance(exc, ValueError):
        return OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc))
    return OctopError(ErrorCode.INTERNAL_ERROR, f"cannot {operation} {path!r}: {exc}")


def _ensure_editable_doc(path: str) -> DocConverter:
    """Return the registered converter for *path* or reject with a 400."""
    converter = get_doc_converter(path)
    if converter is None:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"unsupported editable document {path!r}",
        )
    return converter


def _agent_id_from_media_source(source: str) -> str | None:
    match = re.search(r"/agents/([A-Z0-9]+)/", source, re.IGNORECASE)
    return match.group(1) if match else None


def _workspace_io_path(path: str, *, from_workspace: bool = False) -> str:
    """Resolve an API path for ``BackendWorkspace``.

    ``file://`` is always a host absolute path.

    When ``from_workspace`` is true (workspace UI): leading ``/`` is relative to
    the agent workspace dir (``/logo.png`` → ``logo.png``).

    When false (default, chat/tool downloads): leading ``/`` is a host
    filesystem absolute (``/Users/…``, ``/root/…``). Paths without a leading
    ``/`` stay workspace-relative (``outbound/a.pptx``).
    """
    raw = path.strip()
    if raw.startswith("file://"):
        resolved = backend_workspace_path(raw)
        if resolved is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"cannot resolve {path!r}")
        return resolved
    if from_workspace:
        return workspace_api_path(raw)
    if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":") or raw.startswith("\\\\"):
        return raw
    return workspace_api_path(raw)


_FROM_WORKSPACE_DESC = (
    "When true, leading '/' paths are workspace-relative (workspace UI). "
    "When false (default), leading '/' is host-absolute."
)


router = APIRouter()


@router.get("/agents/{agent_id}/workspace/tree")
async def list_tree(
    agent_id: str,
    path: str = "/",
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """Single-level directory listing under ``path`` (agent must be running)."""
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    io_path = _workspace_io_path(path, from_workspace=from_workspace)
    result = await ws.als(io_path)
    if result is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot list {path!r}")
    entries = getattr(result, "entries", None) or []
    rows = [file_info_to_dict(f) for f in entries]
    if not is_host_absolute_path(io_path):
        for row in rows:
            row["path"] = reanchor_entry_path(str(row.get("path") or ""), parent=io_path)
    return rows


class WriteFileBody(BaseModel):
    content: str
    """UTF-8 text content. Use ``/upload`` for binary."""


class WriteDocBody(BaseModel):
    content: str
    """Markdown content to convert back into the document format."""


@router.get("/agents/{agent_id}/workspace/file")
async def read_file(
    agent_id: str,
    path: str,
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Read a UTF-8 text file."""
    ws = await require_agent_workspace(agent_id, user=user, as_user=as_user, server=server)
    content = await ws.aread_text(_workspace_io_path(path, from_workspace=from_workspace))
    if content is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot read {path!r}")
    return {"path": path, "content": coerce_read_content(content)}


@router.put("/agents/{agent_id}/workspace/file")
async def write_file(
    agent_id: str,
    body: WriteFileBody,
    path: str,
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Overwrite ``path`` with ``body.content`` (text)."""
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    rel = _assert_workspace_mutable(path, workspace=ws, from_workspace=from_workspace)
    # Pick the converter from the path actually written, not the raw request:
    # they diverge when ``path`` carries ``..`` or a host-absolute spelling.
    converter = get_doc_converter(rel)
    if converter is not None:
        # Editable-document paths are always stored as the binary document
        # format. This matters for workspace "new file": an empty .docx created
        # here must be a valid package so its preview (and edit round-trip)
        # works immediately instead of showing a 0-byte file.
        try:
            data = converter.from_markdown(body.content)
        except Exception as exc:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                f"cannot build document for {path!r}: {exc}",
            ) from exc
    else:
        data = body.content.encode("utf-8")
    try:
        await ws.aupload_bytes(rel, data)
    except Exception as exc:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot write {path!r}: {exc}") from exc
    return {"path": _api_workspace_path(rel, fallback=path), "size": len(data)}


class MoveFileBody(BaseModel):
    destination: str
    """Workspace-relative destination path (e.g. ``/sub/file.txt``)."""


@router.post(
    "/agents/{agent_id}/workspace/mkdir",
    status_code=201,
    summary="Create workspace directory",
)
async def mkdir_workspace_dir(
    agent_id: str,
    path: str,
    from_workspace: bool = Query(
        default=True,
        description="Mutating endpoints always treat paths as workspace-relative.",
    ),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create a directory (and parents) under the agent workspace."""
    _ = from_workspace  # API surface; mutations always use workspace-relative paths.
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    rel = _assert_workspace_mutable(path, workspace=ws)
    try:
        await ws.amkdir(rel)
    except Exception as exc:
        raise _map_workspace_fs_error(exc, operation="mkdir", path=path) from exc
    api_path = path if path.startswith("/") else f"/{path}"
    return {"path": api_path, "is_dir": True}


@router.delete(
    "/agents/{agent_id}/workspace/file",
    status_code=204,
    summary="Delete workspace file or directory",
)
async def delete_workspace_file(
    agent_id: str,
    path: str,
    from_workspace: bool = Query(
        default=True,
        description="Mutating endpoints always treat paths as workspace-relative.",
    ),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Response:
    """Remove a file or directory tree from the agent workspace."""
    _ = from_workspace
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    rel = _assert_workspace_mutable(path, workspace=ws)
    try:
        await ws.adelete(rel)
    except Exception as exc:
        raise _map_workspace_fs_error(exc, operation="delete", path=path) from exc
    return Response(status_code=204)


@router.post(
    "/agents/{agent_id}/workspace/move",
    summary="Move or rename a workspace file or directory",
)
async def move_workspace_file(
    agent_id: str,
    body: MoveFileBody,
    path: str,
    from_workspace: bool = Query(
        default=True,
        description="Mutating endpoints always treat paths as workspace-relative.",
    ),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Move ``path`` to ``body.destination`` (rename when the parent directory is unchanged)."""
    _ = from_workspace
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    src = _assert_workspace_mutable(path, workspace=ws)
    dest = _assert_workspace_mutable(body.destination, workspace=ws)
    try:
        await ws.amove(src, dest)
    except Exception as exc:
        raise _map_workspace_fs_error(exc, operation="move", path=path) from exc
    dest_api = body.destination if body.destination.startswith("/") else f"/{body.destination}"
    return {"path": dest_api}


@router.post("/agents/{agent_id}/workspace/upload")
async def upload_file(
    agent_id: str,
    file: UploadFile = File(...),  # noqa: B008
    path: str | None = Query(default=None),
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Upload a binary file via multipart ``file=@...``."""
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    # Guard the path actually used (``path`` may be omitted, in which case the
    # upload's own filename decides it), and do it before ``file.read()`` so a
    # rejected request never buffers its body. A derived filename is always a
    # workspace name — ``from_workspace`` only describes an explicit ``path``.
    target = path or f"/{file.filename or 'upload.bin'}"
    rel = _assert_workspace_mutable(
        target, workspace=ws, from_workspace=from_workspace if path else True
    )
    data = await file.read()
    try:
        await ws.aupload_bytes(rel, data)
    except Exception as exc:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot upload to {target!r}: {exc}") from exc
    return {"path": _api_workspace_path(rel, fallback=target), "size": len(data)}


@router.get("/agents/{agent_id}/workspace/download")
async def download_file(
    agent_id: str,
    path: str,
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Stream ``path`` back as application/octet-stream.

    See ``from_workspace``: workspace UI uses true; chat/tool downloads use false.
    ``file://`` and other host-absolute paths are allowed for agent/OS tool
    outputs (Desktop, ``~/.octop/agents/…``, workspace tree) but denied for
    sensitive system roots (``/etc``, ``.harness-browser``, ``.octop-browser``, Windows system dirs).
    """
    ws = await require_agent_workspace(agent_id, user=user, as_user=as_user, server=server)
    io_path = _workspace_io_path(path, from_workspace=from_workspace)
    if is_host_absolute_path(io_path) and not is_allowed_host_download_abs_path(
        io_path,
        workspace=ws.workspace_dir,
    ):
        raise OctopError(ErrorCode.FORBIDDEN, f"cannot download {path!r}: path not allowed")

    try:
        file_blob = await ws.adownload_bytes(io_path)
    except PermissionError as exc:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot download {path!r}") from exc
    if file_blob is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot download {path!r}") from None

    fname = io_path.rsplit("/", 1)[-1] or "download.bin"
    return StreamingResponse(
        iter([file_blob]),
        media_type="application/octet-stream",
        headers={"Content-Disposition": content_disposition(fname)},
    )


@router.get("/agents/{agent_id}/workspace/doc")
async def read_doc(
    agent_id: str,
    path: str,
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Read an editable document (e.g. ``.docx``) as Markdown for online editing."""
    converter = _ensure_editable_doc(path)
    ws = await require_agent_workspace(agent_id, user=user, as_user=as_user, server=server)
    io_path = _workspace_io_path(path, from_workspace=from_workspace)
    try:
        blob = await ws.adownload_bytes(io_path)
    except PermissionError as exc:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot read {path!r}") from exc
    if blob is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot read {path!r}")
    try:
        content = converter.to_markdown(blob)
    except Exception as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"cannot parse {path!r}: {exc}") from exc
    return {"path": path, "content": content}


@router.put("/agents/{agent_id}/workspace/doc")
async def write_doc(
    agent_id: str,
    body: WriteDocBody,
    path: str,
    from_workspace: bool = Query(
        default=True,
        description="Mutating endpoints always treat paths as workspace-relative.",
    ),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Convert Markdown *content* back to the document format and overwrite *path*."""
    _ = from_workspace  # Mutations always use workspace-relative paths.
    ws = await require_running_workspace(agent_id, user=user, as_user=as_user, server=server)
    rel = _assert_workspace_mutable(path, workspace=ws)
    converter = _ensure_editable_doc(rel)
    try:
        data = converter.from_markdown(body.content)
    except Exception as exc:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"cannot build document for {path!r}: {exc}",
        ) from exc
    try:
        await ws.aupload_bytes(rel, data)
    except Exception as exc:
        raise _map_workspace_fs_error(exc, operation="write", path=path) from exc
    return {"path": _api_workspace_path(rel, fallback=path), "size": len(data)}


@router.get(
    "/agents/{agent_id}/media/preview",
    summary="Preview image or video",
    response_class=StreamingResponse,
)
async def preview_media(
    agent_id: str,
    source: str = Query(..., description="``file://`` URL or workspace-relative path"),
    mime_type: str | None = Query(default=None, alias="mime_type"),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Stream an image or video inline for dashboard tool-result previews."""
    path_agent = _agent_id_from_media_source(source)
    effective_agent = path_agent or agent_id
    ws = await require_running_workspace(effective_agent, user=user, as_user=as_user, server=server)
    payload = await resolve_preview_payload(
        source=source,
        workspace=ws,
        mime_hint=mime_type or "",
    )
    if payload is None:
        raise OctopError(ErrorCode.NOT_FOUND, "preview not available for this source")
    data, mime = payload

    # The source bytes are user-controlled (uploads, tool outputs). Serving them
    # inline without a sandbox CSP would let a navigated SVG (any image/* type)
    # run scripts on this origin; "sandbox" keeps image/video previews working
    # while disabling script execution in the document itself.
    return StreamingResponse(
        iter([data]),
        media_type=mime,
        headers={
            "Content-Disposition": "inline",
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/agents/{agent_id}/workspace/glob")
async def glob_files(
    agent_id: str,
    pattern: str,
    path: str = "/",
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    root = _workspace_io_path(path, from_workspace=from_workspace)
    if pattern in ("**/*.md", "*.md") and root == ".":
        ls_result = await ws.als(".")
        if ls_result is None:
            raise OctopError(ErrorCode.NOT_FOUND, "glob failed")
        entries = getattr(ls_result, "entries", None) or []
        matches = []
        for f in entries:
            row = file_info_to_dict(f)
            if row.get("is_dir"):
                continue
            entry_path = str(row.get("path") or "")
            if entry_path.endswith(".md"):
                matches.append(row)
        return matches
    glob_result = await ws.aglob(pattern, root)
    if glob_result is None:
        raise OctopError(ErrorCode.NOT_FOUND, "glob failed")
    matches = getattr(glob_result, "matches", None) or []
    return [file_info_to_dict(item) for item in matches]


@router.get("/agents/{agent_id}/workspace/grep")
async def grep_files(
    agent_id: str,
    pattern: str,
    path: str = "/",
    from_workspace: bool = Query(default=False, description=_FROM_WORKSPACE_DESC),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    result = await ws.agrep(pattern, _workspace_io_path(path, from_workspace=from_workspace))
    if result is None:
        raise OctopError(ErrorCode.NOT_FOUND, "grep failed")
    matches = getattr(result, "matches", None) or []
    return [dict(m) for m in matches]


_MAX_WORKSPACE_ARCHIVE_BYTES = 200 * 1024 * 1024


@router.get(
    "/agents/{agent_id}/workspace/archive",
    summary="Download workspace as zip",
    response_class=StreamingResponse,
)
async def export_workspace_archive(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Pack workspace files into a zip archive."""
    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    data = await export_workspace_zip(ws)
    filename = f"workspace-{agent_id}.zip"
    return StreamingResponse(
        iter([data]),
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.post(
    "/agents/{agent_id}/workspace/archive",
    summary="Import workspace zip",
)
async def import_workspace_archive(
    agent_id: str,
    file: UploadFile = File(...),  # noqa: B008
    mode: Literal["merge", "replace"] = Query(default="merge"),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Import a zip archive into the workspace (merge or replace)."""
    raw = await file.read()
    if len(raw) > _MAX_WORKSPACE_ARCHIVE_BYTES:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "workspace archive too large (max 200MB)")
    if not raw:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "empty archive")

    ws = await require_running_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    local_ws = resolve_agent_workspace_dir(server, agent_id)
    result = await import_workspace_zip(
        ws,
        raw,
        mode=mode,
        local_workspace_dir=local_ws,
    )
    return {"ok": True, **result}
