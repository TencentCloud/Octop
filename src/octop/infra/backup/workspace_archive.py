"""Zip export/import for a single agent workspace."""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from octop_harness.backends.utils import materialize_storage_path

from octop.i18n import tr
from octop.infra.agents.builtin_skills import (
    OCTOP_BUILTIN_SKILLS_ROOT,
    is_octop_builtin_skills_path,
)
from octop.infra.agents.workspace.dir import DEFAULT_SYSTEM_FILES_PATH

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace

WorkspaceImportMode = Literal["merge", "replace"]

_SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".venv", "node_modules"})
# WAL index files. SQLite rebuilds them; a live one is memory-mapped and Windows
# rejects truncating it with ``OSError(22)``. The database and ``-wal`` stay.
_SQLITE_SHM_NAMES = frozenset({"memory.sqlite-shm", "checkpoints.sqlite-shm"})

# ``aglob("**/*")`` skips dotfiles/dirs; these patterns recover hidden entries on
# backends that only expose glob (no ``als``).
_HIDDEN_GLOB_PATTERNS = (".**/**", "**/.*")


def _safe_zip_name(name: str) -> str | None:
    raw = name.replace("\\", "/").strip().lstrip("/")
    if not raw or raw.endswith("/"):
        return None
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def _entry_rel_path(item: Any) -> tuple[str | None, bool]:
    if isinstance(item, dict):
        path = item.get("path")
        is_dir = bool(item.get("is_dir"))
    else:
        path = getattr(item, "path", None)
        is_dir = bool(getattr(item, "is_dir", False))
    if not path:
        return None, False
    storage = str(path).replace("\\", "/")
    return storage.lstrip("/") or None, is_dir


def _normalize_listed_path(storage: str, workspace_dir: Path) -> str | None:
    """Map a backend/listing path to a workspace-relative zip member name."""
    raw = storage.replace("\\", "/")
    ws_root = str(workspace_dir).replace("\\", "/").rstrip("/")
    if raw == ws_root or raw.startswith(ws_root + "/"):
        rel = raw[len(ws_root) :].lstrip("/")
        return rel or None
    return raw.lstrip("/") or None


def _list_local_file_paths(workspace_dir: Path) -> list[str]:
    """Walk the host workspace tree, including hidden dirs like ``.octop``."""
    root = workspace_dir.resolve()
    if not root.is_dir():
        return []
    paths: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIR_NAMES]
        for name in filenames:
            full = Path(dirpath) / name
            if not full.is_file():
                continue
            paths.append(full.relative_to(root).as_posix())
    return sorted(set(paths))


async def _list_via_als(workspace: BackendWorkspace) -> list[str] | None:
    """Recursively list files via ``als`` (includes hidden entries)."""
    if getattr(workspace.backend, "als", None) is None:
        return None
    paths: list[str] = []
    queue: list[str] = ["."]
    seen_dirs: set[str] = set()
    while queue:
        current = queue.pop()
        if current in seen_dirs:
            continue
        seen_dirs.add(current)
        result = await workspace.als(current)
        if result is None:
            if current == ".":
                return None
            continue
        for item in getattr(result, "entries", None) or []:
            rel, is_dir = _entry_rel_path(item)
            if rel is None:
                continue
            rel = _normalize_listed_path(rel, Path(workspace.workspace_dir))
            if rel is None:
                continue
            name = PurePosixPath(rel).name
            if name in _SKIP_DIR_NAMES:
                continue
            if is_dir:
                queue.append(rel)
            else:
                paths.append(rel)
    return sorted(set(paths))


async def _list_via_aglob(workspace: BackendWorkspace) -> list[str]:
    """Fallback listing when there is no local mount and no ``als``."""
    paths: set[str] = set()
    for pattern in ("**/*", *_HIDDEN_GLOB_PATTERNS):
        result = await workspace.aglob(pattern, ".")
        if result is None:
            continue
        for item in getattr(result, "matches", None) or []:
            rel, is_dir = _entry_rel_path(item)
            if not rel or is_dir:
                continue
            normalized = _normalize_listed_path(rel, Path(workspace.workspace_dir))
            if not normalized:
                continue
            if any(part in _SKIP_DIR_NAMES for part in PurePosixPath(normalized).parts):
                continue
            paths.add(normalized)
    return sorted(paths)


async def _list_file_paths(workspace: BackendWorkspace) -> list[str]:
    """List every packable workspace file, including ``.octop`` / ``outbound`` / ``.env``."""
    if _local_mount(workspace) is not None:
        paths = await asyncio.to_thread(_list_local_file_paths, Path(workspace.workspace_dir))
    else:
        via_als = await _list_via_als(workspace)
        paths = via_als if via_als is not None else await _list_via_aglob(workspace)
    return await asyncio.to_thread(_without_managed_sqlite_shm, workspace, paths)


def _clear_local_workspace(workspace_dir: Path) -> None:
    """Clear visible local workspace content before a replace import.

    Hidden entries (``.octop``, ``.env``, …) stay on disk: older archives may omit
    them, and wiping system state that the zip never restores would destroy
    sessions/auth. Other files from the archive are still written afterwards.
    Octop's SQLite ``-shm`` files are not: a root-level one is left in place, and
    the import never writes ``-shm`` back.
    """
    if not workspace_dir.is_dir():
        return
    for child in workspace_dir.iterdir():
        if (
            child.name in _SKIP_DIR_NAMES
            or _is_root_sqlite_shm(child)
            or child.name.startswith(".")
        ):
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


def _same_local_file(path: Path, other: Path) -> bool:
    """True when both paths name the same file, including case-insensitive volumes."""
    try:
        return path.samefile(other)
    except OSError:
        return False


def _managed_shm_parents(workspace: BackendWorkspace) -> frozenset[str]:
    """System locations that hold Octop's own SQLite files."""
    parents = {".", DEFAULT_SYSTEM_FILES_PATH}
    configured = workspace.system_files_path.strip("/")
    if configured:
        parents.add(configured)
    return frozenset(parents)


def _is_root_sqlite_shm(path: Path) -> bool:
    """A workspace-root SHM file replace-cleanup must not unlink.

    Hidden system dirs are already kept. A legacy database lives at the workspace
    root, and unlinking its mapped ``-shm`` fails on Windows the same way an
    overwrite does. A different-cased name is kept only when the volume treats it
    as that same file.
    """
    if not path.is_file():
        return False
    if path.name in _SQLITE_SHM_NAMES:
        return True
    if path.name.casefold() not in _SQLITE_SHM_NAMES:
        return False
    return _same_local_file(path, path.with_name(path.name.casefold()))


def _is_managed_sqlite_shm(workspace: BackendWorkspace, rel: str) -> bool:
    """Octop-managed ``-shm`` at the legacy root or the system-files directory.

    Exact names are always skipped. A different-cased alias is skipped only when
    a local mount reports it is the same file, so a case-sensitive remote key
    such as ``.OCTOP/MEMORY.SQLITE-SHM`` is left alone.
    """
    path = PurePosixPath(rel.replace("\\", "/").lstrip("/"))
    if path.name.casefold() not in _SQLITE_SHM_NAMES:
        return False
    parents = _managed_shm_parents(workspace)
    parent = path.parent.as_posix()
    if path.name in _SQLITE_SHM_NAMES and parent in parents:
        return True
    if parent.casefold() not in {item.casefold() for item in parents}:
        return False
    if _local_mount(workspace) is None:
        return False
    root = workspace.workspace_dir
    candidate = root / path
    return any(
        _same_local_file(candidate, root / directory / path.name.casefold())
        for directory in parents
        if directory.casefold() == parent.casefold()
    )


def _without_managed_sqlite_shm(workspace: BackendWorkspace, paths: list[str]) -> list[str]:
    return [path for path in paths if not _is_managed_sqlite_shm(workspace, path)]


def _without_managed_sqlite_shm_pairs(
    workspace: BackendWorkspace, pairs: list[tuple[str, bytes]]
) -> list[tuple[str, bytes]]:
    return [(rel, blob) for rel, blob in pairs if not _is_managed_sqlite_shm(workspace, rel)]


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
    locale: str = "en",
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

    # ``DELETE`` / ``move`` refuse this prefix, so writing it from an archive would
    # leave entries the user cannot remove; the files Octop owns are re-seeded on
    # every agent start anyway.
    pairs = [(rel, blob) for rel, blob in entries if not is_octop_builtin_skills_path(rel)]
    skipped = len(entries) - len(pairs)
    if skipped:
        warnings.append(
            f"skipped {skipped} {OCTOP_BUILTIN_SKILLS_ROOT!r} entry/entries (owned by Octop)"
        )
    upload_pairs = await asyncio.to_thread(_without_managed_sqlite_shm_pairs, workspace, pairs)
    skipped_shm = len(pairs) - len(upload_pairs)
    if skipped_shm:
        warnings.append(tr("workspace_archive.skipped_sqlite_shm", locale, count=skipped_shm))
    if upload_pairs:
        await workspace.aupload_many(upload_pairs)

    return {
        "mode": mode,
        "imported": len(upload_pairs),
        "warnings": warnings,
    }
