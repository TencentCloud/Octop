"""Zip export/import for a single agent workspace."""

from __future__ import annotations

import asyncio
import io
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from harness_agent.backends.utils import materialize_storage_path

if TYPE_CHECKING:
    from harness_agent.backends.workspace import BackendWorkspace

WorkspaceImportMode = Literal["merge", "replace"]

_SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".venv", "node_modules"})


def _safe_zip_name(name: str) -> str | None:
    raw = name.replace("\\", "/").strip().lstrip("/")
    if not raw or raw.endswith("/"):
        return None
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(part == ".." for part in parts):
        return None
    return "/".join(parts)


async def _list_file_paths(workspace: BackendWorkspace) -> list[str]:
    result = await workspace.aglob("**/*", ".")
    if result is None:
        return []
    matches = getattr(result, "matches", None) or []
    paths: list[str] = []
    for item in matches:
        if isinstance(item, dict):
            path = item.get("path")
            is_dir = item.get("is_dir")
        else:
            path = getattr(item, "path", None)
            is_dir = getattr(item, "is_dir", False)
        if not path or is_dir:
            continue
        storage = str(path)
        ws_root = str(workspace.workspace_dir)
        if storage.startswith(ws_root):
            rel = storage[len(ws_root) :].lstrip("/\\")
            if rel:
                paths.append(rel)
                continue
        paths.append(storage.lstrip("/"))
    return sorted(set(paths))


def _clear_local_workspace(workspace_dir: Path) -> None:
    """Clear local workspace content, keeping entries an archive cannot restore.

    The export glob never matches hidden paths, so harness system state (``.octop``
    sessions / skills / auth, legacy ``.octop-auth``, ``.env``) is absent from every
    archive. Deleting it here would destroy data the import can never put back, so
    hidden entries are left untouched.
    """
    if not workspace_dir.is_dir():
        return
    for child in workspace_dir.iterdir():
        if child.name in _SKIP_DIR_NAMES or child.name.startswith("."):
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _iter_zip_entries(data: bytes) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            safe = _safe_zip_name(info.filename)
            if safe is None:
                continue
            out.append((safe, zf.read(info)))
    return out


def _local_mount(workspace: BackendWorkspace) -> Path | None:
    """Host disk mount backing *workspace*, or ``None`` when files live elsewhere.

    Mirrors harness ``_has_backend_mount``: sandbox backends keep content inside
    the sandbox, and remote backends (COS/S3/…) expose no local mount. Only a
    host-mounted workspace may be read from an explicit local path.
    """
    backend = workspace.backend
    if getattr(backend, "sandbox_fs", False):
        return None
    return materialize_storage_path("/", backend=backend, must_exist=False)


def _read_entry_bytes(workspace: BackendWorkspace, rel: str) -> bytes | None:
    """Read one workspace entry without backend-root shadowing (blocking).

    ``BackendWorkspace`` probes ``{root_dir}/{rel}`` ahead of ``{workspace_dir}/{rel}``
    under ``virtual_mode``, so a same-named file at the backend root (e.g. a user's
    ``~/AGENTS.md``) would otherwise be packed in place of the workspace's own file.

    Host-mounted workspaces are therefore read from ``workspace_dir`` — the base
    ``present_path`` reports entries against — rather than through
    ``resolve_path()``, which re-maps system entries (``skills/``, ``agents/``,
    ``sessions/``, …) under ``system_files_path`` and would miss a workspace that
    still keeps them at its root. Names escaping the workspace are skipped rather
    than packed. Remote and sandbox backends keep going through the backend
    protocol so stale local files cannot shadow remote objects.

    Kept synchronous so callers can run it in one thread hop (see
    :func:`export_workspace_zip`) instead of blocking the event loop.
    """
    if _local_mount(workspace) is not None:
        root = workspace.workspace_dir
        local = (root / rel).resolve()
        try:
            local.relative_to(root)
        except ValueError:
            return None
        if local.is_file():
            blob = workspace.download_bytes(str(local))
            if blob is not None:
                return blob
    return workspace.download_bytes(rel)


async def export_workspace_zip(workspace: BackendWorkspace) -> bytes:
    """Pack workspace files into a zip archive."""
    paths = await _list_file_paths(workspace)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            blob = await asyncio.to_thread(_read_entry_bytes, workspace, path)
            if blob is None:
                continue
            zf.writestr(path.lstrip("/"), blob)
    return buf.getvalue()


async def import_workspace_zip(
    workspace: BackendWorkspace,
    data: bytes,
    *,
    mode: WorkspaceImportMode,
    local_workspace_dir: Path | None = None,
) -> dict[str, int | str | list[str]]:
    """Import a zip archive into the workspace."""
    entries = _iter_zip_entries(data)
    warnings: list[str] = []

    if mode == "replace" and local_workspace_dir is not None:
        _clear_local_workspace(local_workspace_dir)
    elif mode == "replace":
        warnings.append(
            "replace mode cleared only the local harness workspace; remote-only files may remain"
        )

    pairs = [(rel_path, blob) for rel_path, blob in entries]
    if pairs:
        await workspace.aupload_many(pairs)

    return {
        "mode": mode,
        "imported": len(pairs),
        "warnings": warnings,
    }
