"""Binary file I/O and dashboard media preview through ``agent.workspace``.

Dashboard / gateway code uses this module — **not**
:class:`~octop.infra.gateway.media.ingress.AgentBackedMediaBackend`,
which is only the harness-gateway ``MediaBackend`` adapter for IM ingress.

Path rule for ``BackendWorkspace``
----------------------------------
Prefer workspace-relative ``outbound/`` / ``inbound/`` keys when present in the
source. Otherwise pass the original absolute/relative path through unchanged —
do not rewrite or collapse forms. When BackendWorkspace cannot open a host
absolute path (notably Windows drive-letter paths), fall back to a guarded
host ``Path.read_bytes`` for allowlisted locations.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import mimetypes
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

from octop.infra.gateway.media.constants import OUTBOUND_DIR
from octop.infra.utils.browser_media import legacy_harness_screenshots_dir

if TYPE_CHECKING:
    from harness_agent.backends.workspace import BackendWorkspace

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Host filesystem path guards
# ---------------------------------------------------------------------------

_BLOCKED_UNIX_PREFIXES = (
    "/users/",
    "/tmp/",
    "/home/",
    "/var/",
    "/private/",
    "/appdata/local/temp/",
    "/appdata/local/microsoft/windows/inetcache/",
)

_BLOCKED_WIN_DRIVE_PREFIXES = (
    "c:/users/",
    "c:/windows/temp/",
    "c:/program files/",
    "c:/program files (x86)/",
)


def _normalize_host_path(raw: str) -> str:
    """Lowercase path with forward slashes for prefix checks."""
    text = raw.strip().replace("\\", "/")
    if len(text) >= 2 and text[1] == ":":
        return text.lower()
    if text and not text.startswith("/"):
        text = "/" + text
    return text.lower()


def is_blocked_host_download_path(raw: str) -> bool:
    """True when *raw* looks like a host absolute path that must not be downloaded.

    Workspace-relative keys (``tmp/foo``, ``var/data.json``) must **not** be blocked —
    only paths that are already host-absolute (leading ``/``, ``file://``, or a drive
    letter on Windows).
    """
    text = raw.strip()
    if not text:
        return False

    lowered = text.replace("\\", "/").lower()
    if ".harness-browser" in lowered:
        return True

    if len(text) >= 2 and text[1] == ":":
        norm = _normalize_host_path(text)
        return norm.startswith(_BLOCKED_WIN_DRIVE_PREFIXES)

    if text.startswith("/"):
        norm = _normalize_host_path(text)
        return norm.startswith(_BLOCKED_UNIX_PREFIXES)

    return False


def is_allowed_host_temp_path(resolved: Path) -> bool:
    """True when *resolved* is a regular file under an OS temp directory."""
    try:
        if not resolved.is_file():
            return False
    except OSError:
        return False

    if os.name == "nt":
        candidates: list[Path] = []
        for key in ("TEMP", "TMP"):
            value = os.environ.get(key, "").strip()
            if value:
                candidates.append(Path(value).resolve())
        local_app = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app:
            candidates.append((Path(local_app) / "Temp").resolve())
        with contextlib.suppress(OSError):
            candidates.append(Path(tempfile.gettempdir()).resolve())
        for root in candidates:
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    candidates = []
    with contextlib.suppress(OSError):
        candidates.append(Path(tempfile.gettempdir()).resolve())
    for root in candidates:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    norm = str(resolved).replace("\\", "/")
    return norm.startswith(("/tmp/", "/private/tmp/"))


_PREVIEW_IMAGE = frozenset(
    {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/svg+xml"}
)
_PREVIEW_VIDEO = frozenset({"video/mp4", "video/webm", "video/quicktime", "video/ogg"})


def file_url_to_abs_path(file_url: str) -> str:
    parsed = urllib.parse.urlparse(file_url)
    path = parsed.path
    # file:///C:/… — Windows drive in URL path
    if len(path) >= 3 and path[0] == "/" and path[2] == ":":
        return path[1:]
    # Unix absolute (file:///Users/…) — keep forward slashes; url2pathname
    # would produce \Users\… on Windows and break cross-platform semantics.
    if path.startswith("/"):
        return urllib.parse.unquote(path)
    return urllib.request.url2pathname(path)


def agent_id_from_workspace_path(path: str) -> str | None:
    match = re.search(r"/agents/([A-Z0-9]+)/", path, re.IGNORECASE)
    return match.group(1) if match else None


def resolve_media_agent_id(chat_agent_id: str, raw_url: str) -> str:
    return agent_id_from_workspace_path(raw_url) or chat_agent_id


def extract_workspace_rel(path: str) -> str | None:
    """Return ``outbound/…`` or ``inbound/…`` when present in *path* (any common shape)."""
    raw = path.strip()
    fs_path = file_url_to_abs_path(raw) if raw.startswith("file://") else raw.lstrip("/")
    normalized = fs_path.replace("\\", "/")
    if normalized.startswith(("outbound/", "inbound/")):
        return normalized
    for marker in ("/outbound/", "/inbound/"):
        if marker in normalized:
            return normalized[normalized.index(marker) + 1 :]
    return None


def normalize_workspace_media_path(path: str) -> str:
    """Return ``outbound/…`` or ``inbound/…`` for tool/browser media URLs."""
    rel = extract_workspace_rel(path)
    if rel:
        return rel
    raise ValueError(f"not a workspace media path: {path.strip()!r}")


def normalize_workspace_download_path(path: str) -> str:
    """Backend-relative path for workspace download; rejects host absolute paths."""
    raw = path.strip()
    if not raw:
        raise ValueError("empty path")
    rel = extract_workspace_rel(raw)
    if rel:
        return rel
    if raw.startswith("file://"):
        raise ValueError(f"not a workspace file URL: {raw!r}")
    if is_blocked_host_download_path(raw):
        raise ValueError(f"host path not allowed: {raw!r}")
    return raw.lstrip("/")


def workspace_download_url(agent_id: str, workspace_path: str) -> str:
    """Build a dashboard download URL for a workspace or host-absolute path.

    Absolute / ``file://`` paths are passed through (``from_workspace=false``
    default treats leading ``/`` as host-absolute). Relative workspace keys
    are passed without a leading slash so they stay workspace-relative.
    """
    raw = workspace_path.strip()
    if (
        raw.startswith("file://")
        or raw.startswith("/")
        or (len(raw) >= 2 and raw[1] == ":")
        or raw.startswith("\\\\")
    ):
        path_param = raw
    else:
        rel = extract_workspace_rel(raw) or raw.lstrip("/")
        path_param = rel
    return (
        f"/api/agents/{agent_id}/workspace/download?path={urllib.parse.quote(path_param, safe='')}"
    )


def media_preview_url(agent_id: str, source: str, mime_hint: str = "") -> str:
    params: dict[str, str] = {"source": source}
    if mime_hint:
        params["mime_type"] = mime_hint
    return f"/api/agents/{agent_id}/media/preview?{urllib.parse.urlencode(params)}"


def backend_workspace_path(source: str) -> str | None:
    """Single path to pass to ``BackendWorkspace`` for *source*.

    Absolute (``/…`` or ``file://…``) → absolute host/workspace path, unchanged.
    Relative → relative, unchanged (no leading-slash stripping beyond file://).
    """
    raw = (source or "").strip()
    if not raw:
        return None
    if raw.startswith("file://"):
        return file_url_to_abs_path(raw)
    return raw


def dashboard_media_url(agent_id: str, raw_url: str, mime: str = "") -> str | None:
    """Sync dashboard URL — preserve absolute tool paths as ``file://`` preview sources."""
    media_agent = resolve_media_agent_id(agent_id, raw_url)
    raw = raw_url.strip()
    if not raw:
        return None
    if raw.startswith("file://"):
        return media_preview_url(media_agent, raw, mime)
    if raw.startswith("/"):
        return media_preview_url(media_agent, f"file://{raw}", mime)
    return media_preview_url(media_agent, raw, mime)


async def resolve_dashboard_media_url(
    workspace: BackendWorkspace,
    agent_id: str,
    raw_url: str,
    *,
    filename: str = "",
    mime: str = "",
) -> str:
    """Import external files when needed; preview URL keeps the original path shape."""
    media_agent = resolve_media_agent_id(agent_id, raw_url)
    raw = raw_url.strip()
    if raw.startswith("file://"):
        await ensure_workspace_media_path(workspace, raw, filename=filename, mime=mime)
        return media_preview_url(media_agent, raw, mime)
    if raw.startswith("/"):
        file_url = f"file://{raw}"
        await ensure_workspace_media_path(workspace, file_url, filename=filename, mime=mime)
        return media_preview_url(media_agent, file_url, mime)
    return media_preview_url(media_agent, raw, mime)


def _guess_mime(path: str, hint: str = "") -> str:
    if hint:
        return hint.split(";", 1)[0].strip().lower()
    guessed, _ = mimetypes.guess_type(path)
    return (guessed or "application/octet-stream").lower()


def is_previewable_mime(mime: str) -> bool:
    base = mime.split(";", 1)[0].strip().lower()
    return base in _PREVIEW_IMAGE or base in _PREVIEW_VIDEO


def _abs_path_allowed(abs_path: str, *, workspace: Path) -> bool:
    try:
        resolved = Path(abs_path).resolve()
    except (OSError, ValueError):
        return False
    if is_allowed_host_temp_path(resolved):
        return True
    ws = workspace.resolve()
    for prefix in (
        ws / "outbound",
        ws / "inbound",
        legacy_harness_screenshots_dir().resolve(),
    ):
        try:
            resolved.relative_to(prefix)
            return True
        except ValueError:
            continue
    return False


_DENIED_HOST_DOWNLOAD_PREFIXES = (
    "/etc/",
    "/proc/",
    "/sys/",
    "/dev/",
    "/private/etc/",
)
_DENIED_WIN_DOWNLOAD_PREFIXES = (
    "c:/windows/",
    "c:/program files/",
    "c:/program files (x86)/",
)


def is_allowed_host_download_abs_path(path: str, *, workspace: Path) -> bool:
    """Allow host-absolute download when under workspace / agents / temp, or
    non-system user paths (e.g. Desktop tool outputs). Deny OS system roots.
    """
    raw = path.strip()
    if not raw:
        return False
    if raw.startswith("file://"):
        raw = file_url_to_abs_path(raw)
        if not raw:
            return False

    raw_norm = raw.replace("\\", "/")
    # POSIX-style absolute paths (leading /, not a drive letter) — deny system
    # roots on every platform; Path.resolve() on Windows maps /etc → C:\etc.
    if (
        raw_norm.startswith("/")
        and not (len(raw_norm) >= 3 and raw_norm[2] == ":")
        and any(raw_norm.lower().startswith(prefix) for prefix in _DENIED_HOST_DOWNLOAD_PREFIXES)
    ):
        return False

    try:
        resolved = Path(raw).resolve()
    except (OSError, ValueError):
        return False

    norm = str(resolved).replace("\\", "/").lower()
    if ".harness-browser" in norm:
        return False

    try:
        resolved.relative_to(workspace.resolve())
        return True
    except ValueError:
        pass

    if "/.octop/agents/" in norm:
        return True
    if is_allowed_host_temp_path(resolved):
        return True

    if any(norm.startswith(prefix) for prefix in _DENIED_HOST_DOWNLOAD_PREFIXES):
        return False
    win_denied = (
        len(norm) >= 2
        and norm[1] == ":"
        and any(norm.startswith(prefix) for prefix in _DENIED_WIN_DOWNLOAD_PREFIXES)
    )
    return not win_denied


def is_host_absolute_path(path: str) -> bool:
    """True for host filesystem absolute paths (``/…``, ``file://``, drive letter).

    With ``from_workspace=false``, API leading ``/`` means host-absolute. Workspace
    keys must be passed without a leading slash (``outbound/…``) or with
    ``from_workspace=true``.
    """
    raw = path.strip().replace("\\", "/")
    if raw.startswith("file://"):
        return True
    if len(raw) >= 2 and raw[1] == ":":
        return True
    if raw.startswith("\\\\"):
        return True
    return raw.startswith("/")


def _is_host_absolute(path: str) -> bool:
    return is_host_absolute_path(path)


async def _download_via_workspace(workspace: BackendWorkspace, path: str) -> bytes | None:
    """``adownload_bytes`` that treats path-escape PermissionError as a miss."""
    try:
        return await workspace.adownload_bytes(path)
    except PermissionError:
        return None


async def _read_host_file_bytes(abs_path: str) -> bytes | None:
    """Best-effort host read when BackendWorkspace cannot open a Windows abs path."""
    try:
        return await asyncio.to_thread(Path(abs_path).read_bytes)
    except OSError as exc:
        logger.warning("host file read failed for %s: %s", abs_path, exc)
        return None


async def resolve_preview_payload(
    *,
    source: str,
    workspace: BackendWorkspace,
    mime_hint: str = "",
) -> tuple[bytes, str] | None:
    """Return ``(bytes, mime)`` for an allowed image/video preview source.

    Prefer workspace-relative ``outbound/`` / ``inbound/`` keys (reliable on every
    platform), then the original absolute path via BackendWorkspace, then a
    guarded host ``Path.read_bytes`` fallback. The host fallback matters on
    Windows where drive-letter absolutes are not treated as absolute by
    ``BackendWorkspace.resolve_path`` (``startswith("/")`` only).
    """
    path = backend_workspace_path(source)
    if path is None:
        return None

    rel = extract_workspace_rel(source)
    if rel:
        data = await _download_via_workspace(workspace, rel)
        if data is not None:
            mime = _guess_mime(rel, mime_hint)
            if is_previewable_mime(mime):
                return data, mime

    if _is_host_absolute(path):
        if not _abs_path_allowed(path, workspace=workspace.workspace_dir):
            return None
        data = await _download_via_workspace(workspace, path)
        if data is None:
            data = await _read_host_file_bytes(path)
        used = path
    else:
        data = await _download_via_workspace(workspace, path)
        used = path

    if data is None:
        return None

    mime = _guess_mime(used, mime_hint)
    if not is_previewable_mime(mime):
        return None
    return data, mime


async def read_file_url_bytes(
    workspace: BackendWorkspace,
    file_url: str,
    *,
    filename: str = "",
    mime: str = "",
) -> bytes | None:
    """Read bytes for a ``file://`` URL (workspace, import, or host fallback)."""
    path = backend_workspace_path(file_url)
    if path is None:
        return None

    rel = extract_workspace_rel(file_url)
    if rel:
        data = await _download_via_workspace(workspace, rel)
        if data is not None:
            return data

    data = await _download_via_workspace(workspace, path)
    if data is not None:
        return data

    imported = await ensure_workspace_media_path(workspace, file_url, filename=filename, mime=mime)
    if imported:
        return await _download_via_workspace(workspace, imported)

    if _is_host_absolute(path) and _abs_path_allowed(path, workspace=workspace.workspace_dir):
        return await _read_host_file_bytes(path)
    return None


def _outbound_dest_rel(*, filename: str, abs_path: str, mime: str) -> str:
    ext = Path(filename or abs_path).suffix
    if not ext and mime:
        ext = mimetypes.guess_extension(mime.split(";", 1)[0].strip()) or ""
    stem = Path(filename or abs_path).stem or "attachment"
    return f"{OUTBOUND_DIR}/{int(time.time())}_{stem}{ext}"


async def ensure_workspace_media_path(
    workspace: BackendWorkspace,
    file_url: str,
    *,
    filename: str = "",
    mime: str = "",
) -> str | None:
    """Resolve or import a ``file://`` URL into the agent workspace (``outbound/``)."""
    abs_path = backend_workspace_path(file_url)
    if abs_path is None:
        return None

    existing = extract_workspace_rel(file_url)
    if existing:
        data = await _download_via_workspace(workspace, existing)
        if data is None and _is_host_absolute(abs_path):
            data = await _download_via_workspace(workspace, abs_path)
        if data is not None:
            return existing

    if not _is_host_absolute(abs_path):
        return existing

    dest = _outbound_dest_rel(filename=filename, abs_path=abs_path, mime=mime)
    data = await _download_via_workspace(workspace, abs_path)
    if data is None:
        # Windows drive-letter paths raise PermissionError inside BackendWorkspace
        # before the local backend can open them; read the host file directly.
        data = await _read_host_file_bytes(abs_path)
    if data is None:
        return None
    await workspace.aupload_bytes(dest, data)
    return dest


__all__ = [
    "backend_workspace_path",
    "dashboard_media_url",
    "ensure_workspace_media_path",
    "extract_workspace_rel",
    "file_url_to_abs_path",
    "is_allowed_host_download_abs_path",
    "is_allowed_host_temp_path",
    "is_blocked_host_download_path",
    "is_host_absolute_path",
    "is_previewable_mime",
    "media_preview_url",
    "normalize_workspace_download_path",
    "normalize_workspace_media_path",
    "read_file_url_bytes",
    "resolve_dashboard_media_url",
    "resolve_media_agent_id",
    "resolve_preview_payload",
    "workspace_download_url",
]
