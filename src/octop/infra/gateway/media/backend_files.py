"""Binary file I/O and dashboard media preview through ``agent.workspace``.

Dashboard / gateway code uses this module — **not**
:class:`~octop.infra.gateway.media.ingress.AgentBackedMediaBackend`,
which is only the harness-gateway ``MediaBackend`` adapter for IM ingress.

Path shapes
-----------
Tool / browser media ``source`` strings arrive in several forms:

- **workspace-relative** — ``outbound/chart.png``, ``/outbound/chart.png``
- **workspace file URL** — ``file:///…/agents/{id}/outbound/chart.png``
- **host absolute** — ``file:///tmp/screenshot.png``, ``/tmp/screenshot.png``

:func:`extract_workspace_rel` pulls ``outbound/…`` / ``inbound/…`` from any of the
above. :func:`normalize_workspace_media_path` is the strict variant (raises when not
workspace media). :func:`normalize_workspace_download_path` is for the download API:
workspace paths are allowed; bare host paths are rejected. :func:`parse_media_source`
resolves a preview ``source`` into workspace-relative and/or absolute references.
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
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from octop.infra.gateway.media.constants import OUTBOUND_DIR
from octop.infra.utils.browser_media import legacy_harness_screenshots_dir

if TYPE_CHECKING:
    from harness_agent.backends.workspace import BackendWorkspace

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Host filesystem path guards
#
# Block downloads/previews of host-absolute paths outside the agent workspace
# (Unix + Windows temp/user dirs). Used only by the preview/download paths in
# this module — kept here next to its sole consumer.
# ---------------------------------------------------------------------------

# Unix-style blocked prefixes (normalized to forward slashes, lowercased).
_BLOCKED_UNIX_PREFIXES = (
    "/users/",
    "/tmp/",
    "/home/",
    "/var/",
    "/private/",
    "/appdata/local/temp/",
    "/appdata/local/microsoft/windows/inetcache/",
)

# Extra Windows drive-letter prefixes (lowercase, forward slashes).
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

    # POSIX: /tmp and macOS /private/tmp, plus the process temp dir
    # (macOS TemporaryDirectory uses /var/folders/…, not /tmp).
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
    return urllib.request.url2pathname(parsed.path)


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
    rel = normalize_workspace_media_path(workspace_path)
    return (
        f"/api/agents/{agent_id}/workspace/download?path={urllib.parse.quote('/' + rel, safe='')}"
    )


def media_preview_url(agent_id: str, source: str, mime_hint: str = "") -> str:
    params: dict[str, str] = {"source": source}
    if mime_hint:
        params["mime_type"] = mime_hint
    return f"/api/agents/{agent_id}/media/preview?{urllib.parse.urlencode(params)}"


def dashboard_media_url(agent_id: str, raw_url: str, mime: str = "") -> str | None:
    """Sync dashboard URL when *raw_url* is already workspace media (no backend import)."""
    media_agent = resolve_media_agent_id(agent_id, raw_url)
    rel = extract_workspace_rel(raw_url)
    if rel:
        return workspace_download_url(media_agent, rel)
    if raw_url.startswith("file://"):
        return media_preview_url(media_agent, raw_url, mime)
    return None


async def resolve_dashboard_media_url(
    workspace: BackendWorkspace,
    agent_id: str,
    raw_url: str,
    *,
    filename: str = "",
    mime: str = "",
) -> str:
    """Import if needed, then return workspace download or inline preview URL."""
    media_agent = resolve_media_agent_id(agent_id, raw_url)
    if raw_url.startswith("file://"):
        rel = await ensure_workspace_media_path(workspace, raw_url, filename=filename, mime=mime)
        if rel:
            return workspace_download_url(media_agent, rel)
        return media_preview_url(media_agent, raw_url, mime)
    rel = extract_workspace_rel(raw_url)
    if rel:
        return workspace_download_url(media_agent, rel)
    return media_preview_url(media_agent, raw_url, mime)


@dataclass(frozen=True, slots=True)
class MediaSource:
    """Resolved filesystem reference for a dashboard media ``source`` string."""

    workspace_rel: str | None = None
    abs_path: str | None = None

    def workspace_rels(self, workspace: Path) -> list[str]:
        """All ``outbound/…`` / ``inbound/…`` paths to try, deduped in order."""
        seen: set[str] = set()
        rels: list[str] = []
        for candidate in (
            self.workspace_rel,
            extract_workspace_rel(self.abs_path) if self.abs_path else None,
            _workspace_rel_under_root(self.abs_path, workspace) if self.abs_path else None,
        ):
            if candidate and candidate not in seen:
                seen.add(candidate)
                rels.append(candidate)
        return rels


def parse_media_source(source: str, *, workspace: Path) -> MediaSource | None:
    """Resolve *source* into workspace-relative and/or absolute path components."""
    raw = (source or "").strip()
    if not raw:
        return None

    if raw.startswith("file://"):
        return MediaSource(
            workspace_rel=extract_workspace_rel(raw),
            abs_path=file_url_to_abs_path(raw),
        )

    if raw.startswith("/"):
        abs_path = raw
        return MediaSource(
            workspace_rel=extract_workspace_rel(abs_path)
            or _workspace_rel_under_root(abs_path, workspace),
            abs_path=abs_path,
        )

    stripped = raw.lstrip("/")
    workspace_rel = extract_workspace_rel(stripped)
    if workspace_rel:
        return MediaSource(workspace_rel=workspace_rel)
    if stripped:
        return MediaSource(abs_path=str((workspace / stripped).resolve()))
    return None


def _workspace_rel_under_root(abs_path: str, workspace: Path) -> str | None:
    try:
        rel = str(Path(abs_path).resolve().relative_to(workspace.resolve()))
    except ValueError:
        return None
    if rel.startswith(("outbound/", "inbound/")):
        return rel
    return None


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


async def resolve_preview_payload(
    *,
    source: str,
    workspace: BackendWorkspace,
    mime_hint: str = "",
) -> tuple[bytes, str] | None:
    """Return ``(bytes, mime)`` when *source* is an allowed image/video path."""
    workspace_dir = workspace.workspace_dir
    parsed = parse_media_source(source, workspace=workspace_dir)
    if parsed is None:
        return None

    for rel in parsed.workspace_rels(workspace_dir):
        data = await workspace.adownload_bytes(rel)
        if data is not None:
            mime = _guess_mime(rel, mime_hint)
            if is_previewable_mime(mime):
                return data, mime

    abs_path = parsed.abs_path
    if not abs_path or not _abs_path_allowed(abs_path, workspace=workspace_dir):
        return None

    data = None
    try:
        data = await workspace.adownload_bytes(abs_path)
    except PermissionError:
        data = None
    if data is None:
        try:
            data = await asyncio.to_thread(Path(abs_path).read_bytes)
        except OSError as exc:
            logger.warning("preview read failed for %s: %s", abs_path, exc)
            return None

    mime = _guess_mime(abs_path, mime_hint)
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
    rel = extract_workspace_rel(file_url)
    if rel:
        data = await workspace.adownload_bytes(rel)
        if data is not None:
            return data
    rel = await ensure_workspace_media_path(workspace, file_url, filename=filename, mime=mime)
    if rel:
        return await workspace.adownload_bytes(rel)
    abs_path = file_url_to_abs_path(file_url)
    if abs_path and Path(abs_path).is_file():
        try:
            return await asyncio.to_thread(Path(abs_path).read_bytes)
        except OSError:
            return None
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
    existing = extract_workspace_rel(file_url)
    if existing and await workspace.adownload_bytes(existing) is not None:
        return existing

    abs_path = file_url_to_abs_path(file_url)
    dest = _outbound_dest_rel(filename=filename, abs_path=abs_path, mime=mime)

    data = None
    if abs_path:
        try:
            data = await workspace.adownload_bytes(abs_path)
        except PermissionError:
            data = None
    if data is None and abs_path and Path(abs_path).is_file():
        try:
            data = await asyncio.to_thread(Path(abs_path).read_bytes)
        except OSError:
            data = None
    if data is not None:
        await workspace.aupload_bytes(dest, data)
        return dest
    return None


__all__ = [
    "MediaSource",
    "dashboard_media_url",
    "ensure_workspace_media_path",
    "extract_workspace_rel",
    "file_url_to_abs_path",
    "is_previewable_mime",
    "media_preview_url",
    "normalize_workspace_download_path",
    "normalize_workspace_media_path",
    "parse_media_source",
    "read_file_url_bytes",
    "resolve_dashboard_media_url",
    "resolve_preview_payload",
    "workspace_download_url",
]
