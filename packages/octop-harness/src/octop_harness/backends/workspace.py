"""``BackendWorkspace`` — harness-internal facade for L1 agent storage.

Harness code reads/writes L1 agent-visible / agent-used workspace content
(templates, bootstrap, skills, media, etc.) **only** through this module.
Local runtime persistence that requires real OS fds or database semantics
(memory databases, logs, JSONL conversations, checkpoints) is explicitly
outside this facade.

``workspace_dir`` is the agent's recommended working directory (absolute host
path). ``root_dir`` is a *backend construction* parameter (virtual ``/`` mount)
and is not an agent-facing concept — do not treat the two as peer trees.

Path rules for :meth:`resolve_path`:

* **Relative** (does not start with ``/``) → ``{workspace_dir}/{fragment}``
* **Absolute** (starts with ``/``) → when the backend uses ``virtual_mode``,
  mapped through ``backend._resolve_path`` onto that backend's ``root_dir``;
  otherwise unchanged

``~/…`` is expanded to a host path (still absolute). ``..`` in relative
fragments raises ``PermissionError`` if it escapes ``workspace_dir``.

Under ``virtual_mode`` with a non-host ``root_dir``, :meth:`materialize_local`
(and read helpers) fail back:

* absolute: virtual map under ``root_dir``, then the original host path
* relative: ``{root_dir}/{rel}``, then ``{workspace_dir}/{rel}``

Shell alignment is separate: when Linux + ``virtual_mode`` + non-host
``root_dir`` + ``bwrap`` are available, ``execute`` runs in a directory jail.
Otherwise ``HarnessLocalShellBackend`` conservatively translates credible
virtual command / environment paths and runs from the host workspace.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .utils import (
    BACKEND_CALL_ERRORS,
    BackendOperationNotSupportedError,
    backend_file_exists,
    backend_write_force,
    delete_local_path,
    materialize_storage_path,
    mkdir_local_path,
    move_local_path,
    relative_virtual_path,
)

if TYPE_CHECKING:
    from deepagents.backends.protocol import (
        BackendProtocol,
        GlobResult,
        GrepResult,
        LsResult,
    )

    from octop_harness.builtin._sync import SeedAgentsResult
    from octop_harness.init import InitResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Well-known workspace filenames and defaults (single source of truth)
# ---------------------------------------------------------------------------

USER_FILENAME = "USER.md"
PROACTIVE_FILENAME = "PROACTIVE.md"
DEFAULT_BUILTIN_SKILLS_DIR = "_builtin_skills"
DEFAULT_SKILLS_DIR = "skills"
DEFAULT_AGENTS_DIR = "agents"
DEFAULT_SESSIONS_DIR = "sessions"
DEFAULT_ENV_FILENAME = ".env"
DEFAULT_MEMORY_FILES: tuple[str, ...] = ("AGENTS.md", "MEMORY.md", "USER.md", "SOUL.md")
SYSTEM_DIR_NAMES: frozenset[str] = frozenset(
    {
        DEFAULT_SKILLS_DIR,
        DEFAULT_BUILTIN_SKILLS_DIR,
        DEFAULT_AGENTS_DIR,
        DEFAULT_SESSIONS_DIR,
    }
)
LEGACY_READ_ROOT_DIRS: frozenset[str] = frozenset({DEFAULT_SKILLS_DIR, DEFAULT_AGENTS_DIR})
SYSTEM_FILE_NAMES: frozenset[str] = frozenset(
    {
        ".bootstrapped",
        DEFAULT_ENV_FILENAME,
        "checkpoints.sqlite",
        "memory.sqlite",
        "memory.sqlite-wal",
        "memory.sqlite-shm",
    }
)


def _strip_relative_prefix(fragment: str) -> str:
    if fragment.startswith("./") or fragment.startswith(".\\"):
        return fragment[2:]
    return fragment


def normalize_system_files_path(value: str | Path | None) -> str:
    """Return a workspace-relative system-files prefix, or ``\"\"`` for workspace root."""
    if value is None:
        return ""
    text = str(value).strip().replace("\\", "/")
    if not text or text in {".", "./"}:
        return ""
    if text.startswith("/") or text.startswith("~"):
        msg = f"system_files_path must be workspace-relative, got {value!r}"
        raise ValueError(msg)
    text = text.strip("/")
    if not text or text == ".":
        return ""
    parts = tuple(part for part in text.split("/") if part and part != ".")
    if not parts or any(part == ".." for part in parts):
        msg = f"system_files_path must stay inside the workspace, got {value!r}"
        raise ValueError(msg)
    return "/".join(parts)


def is_system_logical_entry(name: str) -> bool:
    """True when *name* is a well-known system file or directory at workspace root."""
    if name in SYSTEM_DIR_NAMES or name in SYSTEM_FILE_NAMES:
        return True
    return name.startswith("memory.sqlite")


def apply_system_files_prefix(path: str, system_files_path: str) -> str:
    """Prefix well-known system paths when ``system_files_path`` is set.

    Persona markdown (``AGENTS.md``, ``SOUL.md``, …) and other user files are
    unchanged. Paths already under the prefix are left as-is.
    """
    prefix = normalize_system_files_path(system_files_path)
    if not prefix:
        return path
    raw = str(path).strip().replace("\\", "/")
    if not raw or raw in {".", "./"}:
        return path
    leading = raw.startswith("/")
    body = _strip_relative_prefix(raw.lstrip("/"))
    if not body or body == ".":
        return path
    if body == prefix or body.startswith(f"{prefix}/"):
        return path
    first = body.split("/", 1)[0]
    if not is_system_logical_entry(first):
        return path
    prefixed = f"{prefix}/{body}"
    return f"/{prefixed}" if leading else prefixed


def _backend_virtual_mode(backend: object) -> bool:
    value = getattr(backend, "virtual_mode", False)
    return value is True


def _backend_cwd(backend: object) -> Path | None:
    raw = getattr(backend, "cwd", None) or getattr(backend, "root_dir", None)
    if raw is None:
        return None
    return Path(str(raw)).expanduser().resolve()


def _is_host_root_path(path: Path) -> bool:
    try:
        return path.resolve() == Path("/").resolve()
    except OSError:
        return False


def _virtual_key_under_mount(local: Path, backend: object) -> str | None:
    """Map a workspace-local path to a virtual ``/…`` key, or ``None`` if outside mount."""
    if not _backend_virtual_mode(backend):
        return str(local)
    cwd = _backend_cwd(backend)
    if cwd is None:
        return str(local)
    try:
        rel = local.relative_to(cwd)
    except ValueError:
        return None
    text = rel.as_posix()
    if not text or text == ".":
        return "/"
    return f"/{text}"


def _unmap_virtual_key(raw: str, backend: object | None) -> str | None:
    """Host path behind a virtual ``/…`` key, or ``None`` when not applicable."""
    if backend is None or not raw.startswith("/") or not _backend_virtual_mode(backend):
        return None
    resolve_fn = getattr(backend, "_resolve_path", None)
    if not callable(resolve_fn):
        return None
    try:
        return str(resolve_fn(raw))
    except (OSError, PermissionError, ValueError):
        return None


def _present_workspace_path(
    storage_path: str,
    workspace_dir: Path,
    backend: object | None = None,
) -> str:
    """Map a backend storage key to a workspace-relative path for callers.

    Under ``virtual_mode`` the key is a virtual path anchored at the backend
    ``root_dir``; it is un-mapped to its host path before being made relative,
    so a workspace nested under ``root_dir`` still presents ``agents/foo.md``
    instead of the whole virtual key.
    """
    raw = storage_path.strip().replace("\\", "/")
    if not raw:
        return "."
    if backend is not None and is_cloud_storage_backend(backend):
        virt = remote_workspace_virtual_root(workspace_dir)
        rel = relative_virtual_path(raw, virt)
        if rel is not None:
            return rel if rel else "."
    ws = workspace_dir.resolve()
    for text in (_unmap_virtual_key(raw, backend), raw):
        if text is None:
            continue
        candidate = Path(text)
        if text.startswith("~"):
            candidate = candidate.expanduser().resolve()
        else:
            try:
                candidate = candidate.resolve()
            except OSError:
                candidate = Path(text)
        try:
            rel_path = candidate.relative_to(ws)
        except ValueError:
            continue
        posix = rel_path.as_posix()
        return posix if posix else "."
    if raw.startswith("/"):
        return raw.lstrip("/") or "."
    return raw


def _rewrite_row_path(row: Any, *, workspace_dir: Path, backend: object | None = None) -> Any:
    if isinstance(row, dict):
        path = row.get("path")
        if path is None:
            return row
        return {**row, "path": _present_workspace_path(str(path), workspace_dir, backend)}
    path = getattr(row, "path", None)
    if path is None:
        return row
    presented = _present_workspace_path(str(path), workspace_dir, backend)
    try:
        row.path = presented
    except AttributeError:
        return row
    return row


def _download_row_bytes(row: Any) -> bytes | None:
    err = getattr(row, "error", None)
    if err:
        return None
    content = getattr(row, "content", None)
    if content is None:
        return None
    if isinstance(content, str):
        return content.encode("utf-8")
    return bytes(content)


def _raise_upload_errors(responses: list[Any], *, op: str) -> None:
    if not responses:
        raise RuntimeError(f"backend.{op} returned no response")
    for row in responses:
        err = getattr(row, "error", None)
        if err:
            path = getattr(row, "path", None)
            detail = f" for {path!r}" if path else ""
            raise RuntimeError(f"backend {op} error{detail}: {err}")


def _normalize_ls_entries(
    entries: list[Any],
    *,
    workspace_dir: Path,
    backend: object | None = None,
) -> list[Any]:
    return [_rewrite_row_path(entry, workspace_dir=workspace_dir, backend=backend) for entry in entries]


def _normalize_workspace_fragment(path: str) -> str:
    text = str(path).strip().replace("\\", "/")
    if not text or text == "/":
        msg = "cannot operate on workspace root"
        raise ValueError(msg)
    return text.lstrip("/")


def _check_move_into_descendant(src_key: str, dest_key: str, *, src: str) -> None:
    if dest_key.startswith(f"{src_key.rstrip('/')}/"):
        msg = f"cannot move {src!r} into its own descendant"
        raise ValueError(msg)


def _has_backend_mount(backend: object) -> bool:
    """True when the backend exposes a host disk mount for materialize failback.

    Sandbox backends (``sandbox_fs=True``, e.g. Docker) keep agent content
    inside the sandbox — they are not host mounts even if they set path attrs.
    """
    if getattr(backend, "sandbox_fs", False):
        return False
    return materialize_storage_path("/", backend=backend, must_exist=False) is not None


def is_cloud_storage_backend(backend: object) -> bool:
    """True for COS/S3/OSS/OBS/Postgres — object stores with a shared virtual ``/``."""
    try:
        from octop_harness.backends.cloud_storage_base import CloudStorageBackend
    except ImportError:  # pragma: no cover
        return False
    return isinstance(backend, CloudStorageBackend)


def remote_workspace_virtual_root(workspace_dir: Path) -> str:
    """Stable folder under a remote backend's ``/`` for one agent workspace.

    Host paths such as ``~/.octop/agents/<id>`` must not leak into object
    keys. Agent-facing ``/.octop/workspaces/<id>`` is kept as-is. Listing
    the storage root then shows workspace folders instead of a flat dump
    of ``SOUL.md`` / ``skills`` mixed with host-home prefixes.
    """
    text = workspace_dir.as_posix().replace("\\", "/").rstrip("/")
    if text.startswith("/.octop/") or text.startswith("/.agentbuddy/"):
        return text or "/"
    name = workspace_dir.name.strip() or "workspace"
    return f"/.agentbuddy/workspaces/{name}"


def _local_workspace_path(fragment: str, workspace_dir: Path) -> Path:
    local = (workspace_dir / fragment).resolve()
    local.relative_to(workspace_dir.resolve())
    return local


class BackendWorkspace:
    """Facade for harness-internal workspace file I/O via the backend.

    ``read_text`` / ``exists`` fail-soft; ``write_text`` / ``upload_bytes`` raise.
    """

    def __init__(
        self,
        backend: BackendProtocol,
        workspace_dir: str | Path,
        *,
        system_files_path: str | Path | None = None,
    ) -> None:
        self._backend = backend
        self._workspace_dir = Path(workspace_dir).expanduser().resolve()
        self._system_files_path = normalize_system_files_path(system_files_path)

    @property
    def backend(self) -> BackendProtocol:
        return self._backend

    @property
    def workspace_dir(self) -> Path:
        return self._workspace_dir

    @property
    def system_files_path(self) -> str:
        """Workspace-relative prefix for system files, or ``\"\"`` for workspace root."""
        return self._system_files_path

    def system_rel(self, logical: str) -> str:
        """Return the stored workspace-relative fragment for a logical system path."""
        return apply_system_files_prefix(str(logical).replace("\\", "/"), self._system_files_path)

    def _stored_relative(self, path: str) -> str:
        fragment = _strip_relative_prefix(str(path).strip().replace("\\", "/"))
        if not fragment or fragment == ".":
            return fragment
        return apply_system_files_prefix(fragment, self._system_files_path)

    def system_read_roots(self, logical_dir: str) -> list[str]:
        """Workspace-relative directory fragments to scan for reads.

        When ``system_files_path`` is set, legacy workspace-root ``skills/`` and
        ``agents/`` are included before the canonical prefixed paths so callers
        that merge scan results can let the canonical tree win on slug/name
        collisions. Writes still use :meth:`system_rel` only.
        """
        canonical = self.system_rel(logical_dir)
        if not self._system_files_path or logical_dir not in LEGACY_READ_ROOT_DIRS:
            return [canonical]
        if canonical == logical_dir:
            return [canonical]
        return [logical_dir, canonical]

    def _read_fragments(self, path: str) -> list[str]:
        """Ordered workspace-relative fragments to probe on read (canonical first)."""
        s = str(path).strip().replace("\\", "/")
        if s.startswith("~") or s.startswith("/"):
            return [s]
        raw = _strip_relative_prefix(s).lstrip("/")
        if not raw or raw == ".":
            return ["."]
        canonical = self._stored_relative(raw)
        if not self._system_files_path:
            return [canonical]
        prefix = f"{self._system_files_path}/"
        if raw.startswith(prefix):
            legacy = raw[len(prefix) :]
        elif raw.split("/", 1)[0] in LEGACY_READ_ROOT_DIRS:
            legacy = raw
        else:
            legacy = None
        fragments: list[str] = []
        seen: set[str] = set()
        for fragment in (canonical, legacy):
            if fragment and fragment not in seen:
                seen.add(fragment)
                fragments.append(fragment)
        return fragments

    def _resolve_root_fragment(self, fragment: str) -> str:
        """Resolve a workspace-relative fragment without system-path remapping."""
        text = _strip_relative_prefix(fragment.replace("\\", "/"))
        if getattr(self._backend, "sandbox_fs", False):
            return "/" if not text or text == "." else f"/{text}"
        resolved = str((self._workspace_dir / text).resolve())
        Path(resolved).relative_to(self._workspace_dir.resolve())
        return resolved

    def present_path(self, storage_path: str) -> str:
        """Return *storage_path* as a workspace-relative fragment."""
        raw = str(storage_path)
        if getattr(self._backend, "sandbox_fs", False):
            to_virt = getattr(self._backend, "_to_virtual_path", None)
            if callable(to_virt):
                raw = str(to_virt(raw))
        return _present_workspace_path(raw, self._workspace_dir, self._backend)

    def resolve_path(
        self,
        path: str | Path | None,
        *,
        default: str | None = None,
    ) -> str:
        """Resolve *path* for backend I/O and materialization.

        When *path* is ``None``, *default* is used (typical for config overrides).

        * ``/foo`` → under ``virtual_mode``, host path via ``backend._resolve_path``;
          otherwise unchanged
        * ``~/foo`` → expanded host path
        * ``foo`` / ``./foo`` → ``{workspace_dir}/foo``
        """
        if path is None:
            if default is None:
                msg = "resolve_path() requires path or default"
                raise TypeError(msg)
            path = default
        s = str(path)
        if s.startswith("~"):
            return str(Path(s).expanduser().resolve())
        if s.startswith("/"):
            mapped = apply_system_files_prefix(s.replace("\\", "/"), self._system_files_path)
            if getattr(self._backend, "sandbox_fs", False):
                return mapped
            if _backend_virtual_mode(self._backend):
                resolve_fn = getattr(self._backend, "_resolve_path", None)
                if callable(resolve_fn):
                    try:
                        return str(resolve_fn(mapped))
                    except (OSError, PermissionError, ValueError):
                        logger.debug(
                            "BackendWorkspace.resolve_path virtual map failed for %s",
                            mapped,
                            exc_info=True,
                        )
            return mapped
        fragment = self._stored_relative(s)
        if getattr(self._backend, "sandbox_fs", False):
            return "/" if not fragment or fragment == "." else f"/{fragment}"
        resolved = str((self._workspace_dir / fragment).resolve())
        try:
            Path(resolved).relative_to(self._workspace_dir)
        except ValueError as exc:
            msg = f"path {path!r} is outside workspace {self._workspace_dir}"
            raise PermissionError(msg) from exc
        return resolved

    def _backend_storage_key(
        self,
        path: str | Path | None,
        *,
        default: str | None = None,
        map_system_paths: bool = True,
    ) -> str | None:
        """Return a backend protocol key, or ``None`` for local workspace I/O.

        Relative paths are always resolved against this workspace's
        ``workspace_dir`` (the path persisted on the agent). Docker /
        OpenSandbox flatten to a virtual ``/…`` key (the sandbox *is* the
        workspace). COS/S3/OSS/OBS/Postgres nest under
        ``/.octop/workspaces/<id>`` so listing the storage root shows
        workspace folders. Host-mounted backends keep mapping through
        ``root_dir`` / ``cwd``.
        """
        if path is None:
            if default is None:
                msg = "_backend_storage_key() requires path or default"
                raise TypeError(msg)
            path = default
        s = str(path).strip()
        if s.startswith("~"):
            expanded = str(Path(s).expanduser().resolve())
            return self._remap_cloud_absolute(expanded) if is_cloud_storage_backend(self._backend) else expanded
        if s.startswith("/"):
            mapped = apply_system_files_prefix(s.replace("\\", "/"), self._system_files_path)
            return self._remap_cloud_absolute(mapped) if is_cloud_storage_backend(self._backend) else mapped

        fragment = self._stored_relative(s) if map_system_paths else _strip_relative_prefix(s.replace("\\", "/"))
        workspace = self._workspace_dir.resolve()
        if not fragment or fragment == ".":
            local = workspace
            rel_posix = ""
        else:
            local = (workspace / fragment).resolve()
            try:
                rel_posix = local.relative_to(workspace).as_posix()
            except ValueError as exc:
                msg = f"path {path!r} is outside workspace {self._workspace_dir}"
                raise PermissionError(msg) from exc
            if rel_posix == ".":
                rel_posix = ""

        if not _has_backend_mount(self._backend):
            if is_cloud_storage_backend(self._backend):
                root = remote_workspace_virtual_root(workspace)
                return root if not rel_posix else f"{root}/{rel_posix}"
            return "/" if not rel_posix else f"/{rel_posix}"

        return _virtual_key_under_mount(local, self._backend)

    def _remap_cloud_absolute(self, mapped: str) -> str:
        """Map a host or virtual absolute onto the remote workspace folder."""
        virt = remote_workspace_virtual_root(self._workspace_dir)
        raw = str(mapped).replace("\\", "/").rstrip("/") or "/"
        try:
            rel = Path(mapped).resolve().relative_to(self._workspace_dir)
        except (ValueError, OSError):
            rel = None
        if rel is not None:
            posix = rel.as_posix()
            return virt if not posix or posix == "." else f"{virt}/{posix}"
        if raw == virt or raw.startswith(f"{virt}/"):
            return raw
        return mapped if str(mapped).startswith("/") else f"/{mapped}"

    def _legacy_flattened_key(self, fragment: str, *, map_system_paths: bool) -> str | None:
        """Pre-nesting remote key (``/SOUL.md``) for read failback."""
        if not is_cloud_storage_backend(self._backend):
            return None
        text = str(fragment).strip().replace("\\", "/")
        if text.startswith("~") or text.startswith("/"):
            return None
        stored = self._stored_relative(text) if map_system_paths else _strip_relative_prefix(text)
        if not stored or stored == ".":
            return None
        return f"/{stored}"

    def _candidate_storage_keys(
        self,
        path: str,
        *,
        map_system_paths: bool = True,
    ) -> list[str]:
        """Ordered backend keys to probe: nested workspace first, then legacy flatten."""
        keys: list[str] = []
        key = self._backend_storage_key(path, map_system_paths=map_system_paths)
        if key is not None:
            keys.append(key)
        legacy = self._legacy_flattened_key(path, map_system_paths=map_system_paths)
        if legacy is not None and legacy not in keys:
            keys.append(legacy)
        return keys

    def _local_path_for_relative(self, path: str) -> Path:
        return Path(self.resolve_path(path))

    def _mutation_storage_key(self, path: str) -> str | None:
        """Return the backend key used by mkdir/delete/move protocol helpers."""
        key = self._backend_storage_key(path)
        if key is None or _backend_virtual_mode(self._backend) or is_cloud_storage_backend(self._backend):
            return key
        return f"/{self._stored_relative(_normalize_workspace_fragment(path))}"

    def _disk_path_for_mutation(self, path: str) -> Path:
        """Resolve *path* to an on-disk location for mkdir/move/delete fallbacks.

        Workspace-relative paths outside the backend mount stay under
        ``workspace_dir``. Backend keys map through ``backend._resolve_path``;
        when unavailable, a local mount is used as the fallback.
        """
        key = self._backend_storage_key(path)
        if key is None:
            fragment = self._stored_relative(_normalize_workspace_fragment(path))
            return _local_workspace_path(fragment, self._workspace_dir)

        s = str(path).strip().replace("\\", "/")
        if s.startswith("~"):
            return Path(s).expanduser().resolve()

        resolve_fn = getattr(self._backend, "_resolve_path", None)
        if callable(resolve_fn):
            with contextlib.suppress(OSError, PermissionError, ValueError):
                return Path(resolve_fn(key)).resolve()

        cwd = _backend_cwd(self._backend)
        if _backend_virtual_mode(self._backend) and cwd is not None:
            return (cwd / key.lstrip("/")).resolve()
        if s.startswith("/"):
            return Path(s).resolve()
        return _local_workspace_path(self._stored_relative(_normalize_workspace_fragment(path)), self._workspace_dir)

    def _iter_materialize_candidates(
        self,
        path: str,
        *,
        map_system_paths: bool = True,
    ) -> list[Path]:
        """Ordered local paths for read / ``materialize_local`` failback.

        Absolute (``/…`` or ``~``):
          1. virtual map under backend ``root_dir`` when ``virtual_mode``
          2. original host path

        Relative:
          1. ``{root_dir}/{rel}`` when ``virtual_mode`` and root is scoped (≠ ``/``)
          2. ``{workspace_dir}/{rel}``

        When the backend has no local mount (e.g. S3/COS), only workspace-only
        paths (no backend key) use local candidates; otherwise reads go through
        the backend protocol so stale workspace files cannot shadow remote objects.
        """
        raw = str(path).strip().replace("\\", "/")
        if not raw:
            return []

        out: list[Path] = []
        seen: set[str] = set()

        def add(candidate: Path) -> None:
            try:
                key = str(candidate.expanduser().resolve())
            except OSError:
                key = str(candidate)
            if key not in seen:
                seen.add(key)
                out.append(candidate)

        has_mount = _has_backend_mount(self._backend)
        storage_key = self._backend_storage_key(path, map_system_paths=map_system_paths)
        if not has_mount:
            if storage_key is None:
                fragment = self._stored_relative(raw) if map_system_paths else _strip_relative_prefix(raw)
                add(Path(self.resolve_path(fragment)))
            return out

        cwd = _backend_cwd(self._backend)
        virtual = _backend_virtual_mode(self._backend)

        if raw.startswith("~"):
            add(Path(raw).expanduser())
            return out

        if raw.startswith("/"):
            if virtual:
                resolve_fn = getattr(self._backend, "_resolve_path", None)
                if callable(resolve_fn):
                    with contextlib.suppress(OSError, PermissionError, ValueError):
                        add(Path(resolve_fn(raw)))
            add(Path(raw))
            return out

        fragment = self._stored_relative(raw) if map_system_paths else _strip_relative_prefix(raw)
        workspace_candidate = Path(self.resolve_path(fragment))
        if virtual and cwd is not None and not _is_host_root_path(cwd):
            add(cwd / fragment)
        add(workspace_candidate)
        return out

    # ----- Sync I/O -----

    def exists(self, path: str) -> bool:
        for fragment in self._read_fragments(path):
            for candidate in self._iter_materialize_candidates(fragment, map_system_paths=False):
                if candidate.exists():
                    return True
            for key in self._candidate_storage_keys(fragment, map_system_paths=False):
                if backend_file_exists(self._backend, key):
                    return True
        return False

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        for fragment in self._read_fragments(path):
            local = self.materialize_local(fragment, map_system_paths=False)
            if local is not None:
                try:
                    text = local.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    # Fail soft: hosts (e.g. Octop) own repair/skip policy for
                    # third-party skill packages. Never rewrite files here.
                    logger.warning(
                        "BackendWorkspace.read_text local invalid UTF-8 for %s (skipped)",
                        local,
                    )
                except OSError:
                    logger.warning("BackendWorkspace.read_text local failed for %s", local, exc_info=True)
                else:
                    return text if len(text) <= limit else text[:limit]

            for key in self._candidate_storage_keys(fragment, map_system_paths=False):
                try:
                    result = self._backend.read(key, offset=0, limit=limit)
                except BACKEND_CALL_ERRORS:
                    logger.warning("BackendWorkspace.read_text failed for %s", key, exc_info=True)
                    continue
                if result.error is not None or result.file_data is None:
                    continue
                content = result.file_data.get("content", "")
                return content if isinstance(content, str) else None
        return None

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        key = self._backend_storage_key(path)
        if key is None:
            target = self._local_path_for_relative(path)
            if not force and target.exists():
                msg = f"BackendWorkspace.write_text failed for {path!r}: file already exists"
                raise OSError(msg)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return
        storage_path = key
        if force:
            backend_write_force(self._backend, storage_path, content)
            return
        write_result = self._backend.write(storage_path, content)
        if write_result.error is not None:
            raise OSError(f"BackendWorkspace.write_text failed for {storage_path!r}: {write_result.error}")

    def upload_bytes(self, path: str, data: bytes) -> None:
        key = self._backend_storage_key(path)
        if key is None:
            target = self._local_path_for_relative(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return
        responses = self._backend.upload_files([(key, data)])
        _raise_upload_errors(responses, op="upload_files")

    def download_bytes(self, path: str) -> bytes | None:
        """Read file bytes: local materialize failback, then backend storage key."""
        for fragment in self._read_fragments(path):
            local = self.materialize_local(fragment, map_system_paths=False)
            if local is not None:
                try:
                    return local.read_bytes()
                except OSError:
                    logger.warning(
                        "BackendWorkspace.download_bytes local failed for %s",
                        local,
                        exc_info=True,
                    )

            download = getattr(self._backend, "download_files", None)
            if download is None:
                continue
            for key in self._candidate_storage_keys(fragment, map_system_paths=False):
                try:
                    results = download([key])
                except BACKEND_CALL_ERRORS:
                    logger.warning("BackendWorkspace.download_bytes failed for %s", key, exc_info=True)
                    continue
                if not results:
                    continue
                data = _download_row_bytes(results[0])
                if data is not None:
                    return data
        return None

    def list_dir(self, path: str = ".") -> list[Any] | None:
        key = self._backend_storage_key(path)
        if key is None:
            local = self._local_path_for_relative(path) if path not in (".", "") else self._workspace_dir
            if not local.is_dir():
                return None
            entries: list[dict[str, Any]] = []
            for child in sorted(local.iterdir()):
                # Always workspace-relative (``skills/demo``), never basename-only —
                # the dashboard maps entry paths to ``/skills/demo`` API calls.
                rel = child.relative_to(self._workspace_dir).as_posix()
                entries.append({"path": rel, "is_dir": child.is_dir()})
            return entries
        storage_path = key
        ls_fn = getattr(self._backend, "ls", None)
        if ls_fn is None:
            return None
        try:
            result = ls_fn(storage_path)
        except BACKEND_CALL_ERRORS:
            logger.warning("BackendWorkspace.list_dir failed for %s", storage_path, exc_info=True)
            return None
        err = getattr(result, "error", None)
        if err:
            return None
        entries = getattr(result, "entries", None) or []
        return _normalize_ls_entries(
            list(entries),
            workspace_dir=self._workspace_dir,
            backend=self._backend,
        )

    def upload_many(self, pairs: list[tuple[str, bytes]]) -> None:
        if not pairs:
            return
        local_pairs: list[tuple[str, bytes]] = []
        backend_uploads: list[tuple[str, bytes]] = []
        for path, data in pairs:
            key = self._backend_storage_key(path)
            if key is None:
                local_pairs.append((path, data))
            else:
                backend_uploads.append((key, data))
        for path, data in local_pairs:
            self.upload_bytes(path, data)
        if backend_uploads:
            responses = self._backend.upload_files(backend_uploads)
            _raise_upload_errors(responses, op="upload_files")

    # ----- Async I/O -----

    async def aexists(self, path: str) -> bool:
        """Async wrapper around :meth:`exists` with identical read failback."""
        return await asyncio.to_thread(self.exists, path)

    async def aread_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        # Same local failback as ``read_text`` / ``download_bytes`` so virtual
        # ``root_dir`` nests are found when the caller passes a host absolute.
        return await asyncio.to_thread(self.read_text, path, limit=limit)

    async def adownload_bytes(self, path: str) -> bytes | None:
        """Async wrapper around :meth:`download_bytes` (same failback)."""
        return await asyncio.to_thread(self.download_bytes, path)

    async def aupload_bytes(self, path: str, data: bytes) -> None:
        key = self._backend_storage_key(path)
        if key is None:
            await asyncio.to_thread(self.upload_bytes, path, data)
            return
        aupload = getattr(self._backend, "aupload_files", None)
        if aupload is None:
            await asyncio.to_thread(self.upload_bytes, path, data)
            return
        responses = await aupload([(key, data)])
        _raise_upload_errors(responses, op="aupload_files")

    async def awrite_text(self, path: str, content: str, *, force: bool = True) -> None:
        if force:
            await self.aupload_bytes(path, content.encode("utf-8"))
            return
        key = self._backend_storage_key(path)
        if key is None:
            await asyncio.to_thread(self.write_text, path, content, force=False)
            return
        awrite = getattr(self._backend, "awrite", None)
        if awrite is None:
            await asyncio.to_thread(self.write_text, path, content, force=False)
            return
        write_result = await awrite(key, content)
        err = getattr(write_result, "error", None)
        if err:
            raise OSError(f"BackendWorkspace.awrite_text failed for {key!r}: {err}")

    async def als(self, path: str = ".") -> LsResult | None:
        key = self._backend_storage_key(path)
        als_fn = getattr(self._backend, "als", None)
        if key is None or als_fn is None:
            entries = await asyncio.to_thread(self.list_dir, path)
            if entries is None:
                return None
            from deepagents.backends.protocol import LsResult as _LsResult

            return _LsResult(error=None, entries=entries)
        try:
            result = await als_fn(key)
        except BACKEND_CALL_ERRORS:
            logger.warning("BackendWorkspace.als failed for %s", key, exc_info=True)
            return None
        err = getattr(result, "error", None)
        if err:
            return None
        entries = _normalize_ls_entries(
            list(getattr(result, "entries", None) or []),
            workspace_dir=self._workspace_dir,
            backend=self._backend,
        )
        from deepagents.backends.protocol import LsResult as _LsResult

        return _LsResult(error=None, entries=entries)

    async def aglob(self, pattern: str, path: str = ".") -> GlobResult | None:
        aglob_fn = getattr(self._backend, "aglob", None)
        if aglob_fn is None:
            return None
        key = self._backend_storage_key(path)
        if key is None:
            return None
        try:
            result = await aglob_fn(self.system_rel(pattern), key)
        except BACKEND_CALL_ERRORS:
            logger.warning(
                "BackendWorkspace.aglob failed for %s pattern=%s",
                key,
                pattern,
                exc_info=True,
            )
            return None
        err = getattr(result, "error", None)
        if err:
            return None
        matches = _normalize_ls_entries(
            list(getattr(result, "matches", None) or []),
            workspace_dir=self._workspace_dir,
            backend=self._backend,
        )
        from deepagents.backends.protocol import GlobResult as _GlobResult

        return _GlobResult(error=None, matches=matches)

    async def agrep(self, pattern: str, path: str = ".") -> GrepResult | None:
        agrep_fn = getattr(self._backend, "agrep", None)
        if agrep_fn is None:
            return None
        key = self._backend_storage_key(path)
        if key is None:
            return None
        try:
            result = await agrep_fn(pattern, key)
        except BACKEND_CALL_ERRORS:
            logger.warning(
                "BackendWorkspace.agrep failed for %s pattern=%s",
                key,
                pattern,
                exc_info=True,
            )
            return None
        err = getattr(result, "error", None)
        if err:
            return None
        matches = _normalize_ls_entries(
            list(getattr(result, "matches", None) or []),
            workspace_dir=self._workspace_dir,
            backend=self._backend,
        )
        from deepagents.backends.protocol import GrepResult as _GrepResult

        return _GrepResult(error=None, matches=matches)

    async def aupload_many(self, pairs: list[tuple[str, bytes]]) -> None:
        if not pairs:
            return
        local_pairs: list[tuple[str, bytes]] = []
        backend_uploads: list[tuple[str, bytes]] = []
        for path, data in pairs:
            key = self._backend_storage_key(path)
            if key is None:
                local_pairs.append((path, data))
            else:
                backend_uploads.append((key, data))

        if local_pairs:
            await asyncio.to_thread(self.upload_many, local_pairs)
        if not backend_uploads:
            return

        aupload = getattr(self._backend, "aupload_files", None)
        if aupload is None:
            responses = await asyncio.to_thread(self._backend.upload_files, backend_uploads)
            op = "upload_files"
        else:
            responses = await aupload(backend_uploads)
            op = "aupload_files"
        _raise_upload_errors(responses, op=op)

    # ----- Mkdir / delete / move -----

    def mkdir(self, path: str) -> None:
        """Create a directory (and parents) at *path*."""
        key = self._mutation_storage_key(path)
        if key is None:
            fragment = self._stored_relative(_normalize_workspace_fragment(path))
            mkdir_local_path(_local_workspace_path(fragment, self._workspace_dir))
            return
        mkdir_path = getattr(self._backend, "mkdir_path", None)
        if callable(mkdir_path):
            mkdir_path(key)
            return
        if not _has_backend_mount(self._backend):
            raise BackendOperationNotSupportedError("mkdir", type(self._backend).__name__)
        mkdir_local_path(self._disk_path_for_mutation(path))

    async def amkdir(self, path: str) -> None:
        key = self._mutation_storage_key(path)
        if key is None:
            await asyncio.to_thread(self.mkdir, path)
            return
        amkdir_path = getattr(self._backend, "amkdir_path", None)
        if callable(amkdir_path):
            await amkdir_path(key)
            return
        await asyncio.to_thread(self.mkdir, path)

    def delete(self, path: str) -> None:
        """Delete a workspace file or directory tree."""
        key = self._mutation_storage_key(path)
        if key is None:
            fragment = self._stored_relative(_normalize_workspace_fragment(path))
            delete_local_path(_local_workspace_path(fragment, self._workspace_dir))
            return
        delete_path = getattr(self._backend, "delete_path", None)
        if callable(delete_path):
            delete_path(key)
            return
        if not _has_backend_mount(self._backend):
            raise BackendOperationNotSupportedError("delete", type(self._backend).__name__)
        delete_local_path(self._disk_path_for_mutation(path))

    async def adelete(self, path: str) -> None:
        key = self._mutation_storage_key(path)
        if key is None:
            await asyncio.to_thread(self.delete, path)
            return
        adelete_path = getattr(self._backend, "adelete_path", None)
        if callable(adelete_path):
            await adelete_path(key)
            return
        await asyncio.to_thread(self.delete, path)

    def move(self, src: str, dest: str) -> None:
        """Move or rename a workspace file or directory tree."""
        src_key = self._mutation_storage_key(src)
        dest_key = self._mutation_storage_key(dest)
        if src_key is None or dest_key is None:
            # Resolve each side independently: a workspace-relative source and
            # a backend virtual destination may have different disk mappings.
            src_path = self._disk_path_for_mutation(src)
            dest_path = self._disk_path_for_mutation(dest)
            _check_move_into_descendant(str(src_path), str(dest_path), src=src)
            if dest_path.exists():
                msg = f"destination already exists: {dest!r}"
                raise FileExistsError(msg)
            move_local_path(src_path, dest_path)
            return
        _check_move_into_descendant(src_key, dest_key, src=src)
        if src_key == dest_key:
            return
        move_path = getattr(self._backend, "move_path", None)
        if callable(move_path):
            move_path(src_key, dest_key)
            return
        if not _has_backend_mount(self._backend):
            raise BackendOperationNotSupportedError("move", type(self._backend).__name__)
        dest_path = self._disk_path_for_mutation(dest)
        if dest_path.exists():
            msg = f"destination already exists: {dest!r}"
            raise FileExistsError(msg)
        move_local_path(self._disk_path_for_mutation(src), dest_path)

    async def amove(self, src: str, dest: str) -> None:
        src_key = self._mutation_storage_key(src)
        dest_key = self._mutation_storage_key(dest)
        if src_key is None or dest_key is None:
            await asyncio.to_thread(self.move, src, dest)
            return
        _check_move_into_descendant(src_key, dest_key, src=src)
        if src_key == dest_key:
            return
        amove_path = getattr(self._backend, "amove_path", None)
        if callable(amove_path):
            await amove_path(src_key, dest_key)
            return
        await asyncio.to_thread(self.move, src, dest)

    # ----- Local materialization -----

    def materialize_local(self, path: str, *, map_system_paths: bool = True) -> Path | None:
        """Return a local filesystem path for *path* when bytes are available.

        Local / virtual mounts: failback candidates under ``root_dir`` /
        ``workspace_dir``. Sandbox / remote backends (no host mount): download
        into ``{workspace_dir}/.harness-materialize/`` for channel adapters
        (``send_file_to_user``); this cache is delivery-only, not the workspace.
        """
        for candidate in self._iter_materialize_candidates(path, map_system_paths=map_system_paths):
            if candidate.is_file():
                return candidate.resolve()
        key = self._backend_storage_key(path, map_system_paths=map_system_paths)
        if key is None:
            return None
        mounted = materialize_storage_path(key, backend=self._backend, must_exist=True)
        if mounted is not None:
            return mounted.resolve()
        if _has_backend_mount(self._backend):
            return None
        return self._materialize_via_download(key, path)

    def _materialize_via_download(self, key: str, path: str) -> Path | None:
        """Pull *key* from the backend into a host-side delivery cache."""
        download = getattr(self._backend, "download_files", None)
        if not callable(download):
            return None
        try:
            results = download([key])
        except BACKEND_CALL_ERRORS:
            logger.warning("materialize download failed for %s", key, exc_info=True)
            return None
        if not results:
            return None
        data = _download_row_bytes(results[0])
        if data is None:
            return None
        rel = self.present_path(str(path))
        if not rel or rel == ".":
            rel = Path(str(path)).name or "file"
        target = (self._workspace_dir / ".harness-materialize" / rel).resolve()
        try:
            target.relative_to((self._workspace_dir / ".harness-materialize").resolve())
        except ValueError:
            target = self._workspace_dir / ".harness-materialize" / Path(rel).name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    # ----- Deepagents graph path lists -----

    def _deepagents_source_path(
        self,
        path: str | Path,
        *,
        map_system_paths: bool = True,
    ) -> str:
        """Return a source path for deepagents Skills / Memory middleware.

        Those middlewares call ``backend.ls`` / ``download`` and inject the same
        strings into the system prompt. Under ``virtual_mode`` that requires
        agent-facing virtual keys (e.g. ``/.octop/workspaces/<id>/.octop/skills``),
        not host joins from :meth:`resolve_path` (which prepend ``root_dir``).
        """
        key = self._backend_storage_key(path, map_system_paths=map_system_paths)
        if key is not None:
            return key
        # Outside the backend mount (e.g. host-absolute skill-package roots).
        return self.resolve_path(str(path))

    def skill_paths(
        self,
        *,
        extra: str | Path | Sequence[str | Path] | None = None,
    ) -> list[str]:
        paths = [self._deepagents_source_path(DEFAULT_BUILTIN_SKILLS_DIR)]
        for fragment in self.system_read_roots(DEFAULT_SKILLS_DIR):
            # Legacy workspace-root ``skills/`` must not pick up system_files_path.
            map_system = not (fragment == DEFAULT_SKILLS_DIR and bool(self._system_files_path))
            paths.append(self._deepagents_source_path(fragment, map_system_paths=map_system))
        if extra is None:
            return paths

        if isinstance(extra, str | Path):
            extras: list[str | Path] = [extra]
        else:
            extras = [entry for entry in extra]
        for entry in extras:
            paths.append(self._deepagents_source_path(str(entry)))
        return paths

    def skill_catalog_roots(
        self,
        *,
        extra: str | Path | Sequence[str | Path] | None = None,
    ) -> list[tuple[str, str]]:
        """Return ``(root_fragment, kind)`` pairs for scanning ``*/SKILL.md`` manifests.

        Aligns with :meth:`skill_paths` — each *extra* entry is a skill **root**
        directory (container of skill subfolders), not a single skill folder.
        """
        roots: list[tuple[str, str]] = [
            (self.system_rel(DEFAULT_BUILTIN_SKILLS_DIR), "builtin"),
        ]
        for fragment in self.system_read_roots(DEFAULT_SKILLS_DIR):
            roots.append((fragment, "workspace"))
        if extra is None:
            return roots

        entries: list[str | Path] = [extra] if isinstance(extra, str | Path) else list(extra)
        for entry in entries:
            resolved = self.resolve_path(str(entry))
            # Keep host-absolute roots outside the workspace as absolute paths.
            # ``_present_workspace_path`` strips the leading slash for foreign
            # absolutes, which would make catalog ``als`` look under workspace.
            try:
                Path(resolved).resolve().relative_to(self._workspace_dir.resolve())
            except (ValueError, OSError):
                roots.append((resolved, "workspace"))
                continue
            fragment = _present_workspace_path(resolved, self._workspace_dir)
            roots.append((fragment, "workspace"))
        return roots

    def memory_paths(self, override: Sequence[str] | None = None, *, include_missing: bool = False) -> list[str]:
        """Resolve unified context sources for deepagents' memory loader.

        Include missing paths when assembling a graph so sources stay stable:
        new sessions can load files created later, and restored sessions still
        format their checkpoint snapshot after a source file is deleted.
        The upstream loader skips missing files itself.
        """
        names = list(DEFAULT_MEMORY_FILES) if override is None else list(override)
        paths: list[str] = []
        for name in names:
            if include_missing or self.exists(name):
                paths.append(self._deepagents_source_path(name))
        return paths

    # ----- High-level workspace operations -----

    def sync_builtin_skills(self, agent_version: str, *, language: str = "en") -> tuple[bool, list[str]]:
        """Copy packaged built-in skills into ``DEFAULT_BUILTIN_SKILLS_DIR``.

        Args:
            agent_version: Package version used as cache key.
            language: Language code (``"en"`` / ``"zh"``).  When the
                language subdirectory does not exist, falls back to ``"en"``.

        Returns:
            ``(synced, fallback_paths)`` where *fallback_paths* lists
            the workspace paths served from the ``"en"`` fallback.
        """
        from octop_harness.builtin._sync import sync_builtin_skills_to_backend

        return sync_builtin_skills_to_backend(self, agent_version, language=language)

    def seed_builtin_agents(self, *, language: str = "en", overwrite: bool = False) -> SeedAgentsResult:
        """Seed packaged built-in agent markdown into ``DEFAULT_AGENTS_DIR``.

        Args:
            language: Language code (``"en"`` / ``"zh"``).  When the
                language subdirectory does not exist, falls back to ``"en"``.
            overwrite: Replace existing files when True.
        """
        from octop_harness.builtin._sync import seed_builtin_agents_to_workspace

        return seed_builtin_agents_to_workspace(self, language=language, overwrite=overwrite)

    def init_workspace(
        self,
        *,
        language: str = "en",
        include_md_files: bool = True,
        include_skills: bool = True,
        include_agents: bool = True,
        overwrite: bool = False,
    ) -> InitResult:
        from octop_harness.init import _seed_workspace

        # Ensure system files root (e.g. ``.octop/``) exists before any
        # system-scoped writes happen during workspace seeding.
        if self._system_files_path:
            self.mkdir(self._system_files_path)

        return _seed_workspace(
            self,
            language=language,
            include_md_files=include_md_files,
            include_skills=include_skills,
            include_agents=include_agents,
            overwrite=overwrite,
        )


__all__ = [
    "DEFAULT_AGENTS_DIR",
    "DEFAULT_BUILTIN_SKILLS_DIR",
    "DEFAULT_MEMORY_FILES",
    "DEFAULT_SKILLS_DIR",
    "LEGACY_READ_ROOT_DIRS",
    "PROACTIVE_FILENAME",
    "USER_FILENAME",
    "BackendWorkspace",
    "apply_system_files_prefix",
    "is_cloud_storage_backend",
    "normalize_system_files_path",
    "remote_workspace_virtual_root",
]
