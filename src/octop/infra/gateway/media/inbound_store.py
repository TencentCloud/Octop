"""Inbound attachment storage — all ingress via :class:`BackendWorkspace`."""

from __future__ import annotations

import mimetypes
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from octop.infra.agents.workspace_dir import (
    agent_facing_workspace_root,
    join_agent_facing,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.media.constants import INBOUND_DIR

if TYPE_CHECKING:
    from harness_agent.backends.workspace import BackendWorkspace

MAX_INBOUND_BYTES = 20 * 1024 * 1024

# Used when the reported MIME is outside ALLOWED_INBOUND_MEDIA_TYPES (e.g. Windows
# registry types like ``application/x-zip-compressed``, or browsers sending
# ``video/mp2t`` for ``.ts``).
INBOUND_EXTENSION_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".jfif": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".ico": "image/vnd.microsoft.icon",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".avif": "image/avif",
    ".apng": "image/apng",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".rst": "text/x-rst",
    ".json": "application/json",
    ".jsonl": "application/jsonl",
    ".ndjson": "application/x-ndjson",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel",
    ".ppt": "application/vnd.ms-powerpoint",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".docm": "application/vnd.ms-word.document.macroEnabled.12",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".pptm": "application/vnd.ms-powerpoint.presentation.macroEnabled.12",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".rtf": "application/rtf",
    ".epub": "application/epub+zip",
    ".xmind": "application/vnd.xmind.workbook",
    ".zip": "application/zip",
    ".7z": "application/x-7z-compressed",
    ".rar": "application/vnd.rar",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".tgz": "application/gzip",
    ".bz2": "application/x-bzip2",
    ".xz": "application/x-xz",
    ".py": "text/x-python",
    ".pyi": "text/x-python",
    ".pyw": "text/x-python",
    ".ipynb": "application/json",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".cjs": "text/javascript",
    ".jsx": "text/javascript",
    ".ts": "text/x-typescript",
    ".tsx": "text/x-typescript",
    ".mts": "text/x-typescript",
    ".cts": "text/x-typescript",
    ".sh": "text/x-shellscript",
    ".bash": "text/x-shellscript",
    ".zsh": "text/x-shellscript",
    ".fish": "text/x-shellscript",
    ".ksh": "text/x-shellscript",
    ".ps1": "text/plain",
    ".bat": "text/plain",
    ".cmd": "text/plain",
    ".go": "text/x-go",
    ".rs": "text/x-rust",
    ".java": "text/x-java-source",
    ".kt": "text/x-kotlin",
    ".kts": "text/x-kotlin",
    ".scala": "text/x-scala",
    ".c": "text/x-c",
    ".h": "text/x-c",
    ".cpp": "text/x-c++",
    ".cc": "text/x-c++",
    ".cxx": "text/x-c++",
    ".hpp": "text/x-c++",
    ".hh": "text/x-c++",
    ".cs": "text/x-csharp",
    ".swift": "text/x-swift",
    ".rb": "text/x-ruby",
    ".php": "text/x-php",
    ".pl": "text/x-perl",
    ".pm": "text/x-perl",
    ".lua": "text/x-lua",
    ".r": "text/x-r",
    ".jl": "text/x-julia",
    ".sql": "application/sql",
    ".html": "text/html",
    ".htm": "text/html",
    ".css": "text/css",
    ".scss": "text/x-scss",
    ".sass": "text/x-sass",
    ".less": "text/x-less",
    ".vue": "text/plain",
    ".svelte": "text/plain",
    ".astro": "text/plain",
    ".xml": "application/xml",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".toml": "application/toml",
    ".ini": "text/plain",
    ".cfg": "text/plain",
    ".conf": "text/plain",
    ".env": "text/plain",
    ".properties": "text/plain",
    ".tf": "text/plain",
    ".hcl": "text/plain",
    ".proto": "text/plain",
    ".graphql": "application/graphql",
    ".gql": "application/graphql",
    ".lock": "text/plain",
    ".log": "text/plain",
    ".diff": "text/x-diff",
    ".patch": "text/x-diff",
    ".mk": "text/x-makefile",
    ".cmake": "text/plain",
    ".gradle": "text/plain",
    ".dockerfile": "text/plain",
}

# Browser / OS registry types that are not the canonical stored MIME.
_INBOUND_MEDIA_TYPE_ALIASES = frozenset(
    {
        "application/javascript",
        "application/x-javascript",
        "application/typescript",
        "text/typescript",
        "application/x-sh",
        "application/x-shellscript",
        "text/x-sh",
        "application/x-python",
        "text/x-script.python",
        "application/x-yaml",
        "text/x-yaml",
        "text/yaml",
        "text/xml",
        "application/x-httpd-php",
        "text/x-sql",
        "application/x-ipynb+json",
        "text/rtf",
        "application/x-rtf",
        "application/x-gzip",
        "application/x-gtar",
        "application/x-rar-compressed",
        "application/x-rar",
        "application/x-bzip",
        "image/x-icon",
        "image/vnd.xmind.workbook",
        "application/x-xmind",
        "application/xmind",
    }
)

ALLOWED_INBOUND_MEDIA_TYPES = frozenset(
    {
        "application/octet-stream",
        *_INBOUND_MEDIA_TYPE_ALIASES,
        *INBOUND_EXTENSION_MEDIA_TYPES.values(),
    }
)

# Display / on-disk names may be non-ASCII; strip path separators / controls only.
_UNSAFE_FILENAME_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')
# ``1783510288_report.pdf`` / ``1783510288_report-2.pdf`` stored names.
_STORED_TS_PREFIX = re.compile(r"^(\d{10,})_(.+)$")


@dataclass(frozen=True)
class InboundFile:
    """A file stored under workspace ``inbound/``."""

    path: str
    filename: str
    media_type: str
    size: int


def normalize_inbound_media_type(media_type: str) -> str:
    return (media_type or "application/octet-stream").split(";", 1)[0].strip().lower()


def inbound_extension(filename: str, media_type: str) -> str:
    """Return a lowercase extension for workspace storage (includes leading dot)."""
    ext = Path(filename or "").suffix.lower()
    if ext:
        return ext
    guessed = mimetypes.guess_extension(normalize_inbound_media_type(media_type)) or ""
    return guessed or ".bin"


def inbound_rel_path(key: str) -> str:
    """Map harness ``MediaBackend`` key to workspace-relative ``inbound/`` path."""
    raw = key.strip().lstrip("/")
    if raw.startswith("inbound/"):
        return raw
    if raw.startswith("outbound/"):
        return raw
    return f"{INBOUND_DIR}/{raw}"


def _backend_mount(workspace: BackendWorkspace) -> tuple[str | None, bool]:
    backend: object = workspace.backend
    target = getattr(backend, "default", backend)
    virtual = bool(getattr(target, "virtual_mode", False)) or bool(
        getattr(backend, "virtual_mode", False)
    )
    root_raw = getattr(target, "root_dir", None) or getattr(target, "cwd", None)
    if root_raw is None:
        return None, virtual
    text = str(root_raw).strip()
    return (text or None), virtual


def agent_facing_workspace_path(workspace: BackendWorkspace, path: str) -> str:
    """Return an agent-visible path for *path* (no host ``root_dir`` prefix).

    Relative keys are joined under the agent-facing workspace root. Absolute
    host paths under the on-disk workspace are remapped the same way.
    """
    raw = (path or "").strip().replace("\\", "/")
    root_raw, virtual = _backend_mount(workspace)
    facing_root = agent_facing_workspace_root(
        workspace.workspace_dir,
        root_dir=root_raw,
        virtual_mode=virtual,
    )
    if raw.startswith("/") and facing_root and facing_root != "/":
        prefix = facing_root.rstrip("/")
        if raw == prefix or raw.startswith(prefix + "/"):
            return raw
    if not raw or raw in {".", "./"}:
        return facing_root or "."
    try:
        host_rel = (
            Path(raw)
            .expanduser()
            .resolve()
            .relative_to(workspace.workspace_dir.resolve())
            .as_posix()
        )
        if host_rel and host_rel != ".":
            return join_agent_facing(facing_root, host_rel)
    except (OSError, ValueError):
        pass
    # inbound/outbound keys go through the same normalizer as attachment storage.
    if (
        raw.startswith(("inbound/", "outbound/"))
        or "/inbound/" in f"/{raw}/"
        or "/outbound/" in f"/{raw}/"
    ):
        return join_agent_facing(facing_root, inbound_rel_path(raw))
    return join_agent_facing(facing_root, raw.lstrip("/"))


def resolve_inbound_attachment_path(workspace: BackendWorkspace, path: str) -> str:
    """Agent-facing path for attachment hints (not a host ``root_dir`` join)."""
    return agent_facing_workspace_path(workspace, path)


def validate_inbound_size(data: bytes) -> None:
    if len(data) > MAX_INBOUND_BYTES:
        max_mb = MAX_INBOUND_BYTES // (1024 * 1024)
        raise OctopError(
            ErrorCode.ATTACHMENT_TOO_LARGE,
            f"file too large (max {max_mb}MB)",
            details={"max_mb": max_mb},
        )


def validate_inbound_media_type(media_type: str, filename: str = "") -> str:
    normalized_type = normalize_inbound_media_type(media_type)
    if normalized_type in ALLOWED_INBOUND_MEDIA_TYPES:
        return normalized_type
    ext = Path(filename or "").suffix.lower()
    mapped = INBOUND_EXTENSION_MEDIA_TYPES.get(ext)
    if mapped is not None:
        return mapped
    reason = f"unsupported media type {normalized_type!r}"
    raise OctopError(ErrorCode.ATTACHMENT_UNSUPPORTED_TYPE, reason, details={"reason": reason})


def sanitize_inbound_filename(filename: str) -> str:
    """Keep the original display name (including CJK); strip only dangerous chars."""
    base = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    base = _UNSAFE_FILENAME_CHARS.sub("_", base).strip(" .") or "upload.bin"
    if len(base) > 180:
        suffix = Path(base).suffix
        stem = base[: 180 - len(suffix)] if suffix else base[:180]
        base = f"{stem}{suffix}" if suffix else stem
    return base or "upload.bin"


def display_name_from_stored(stored_name: str) -> str:
    """Strip ``{unix_ts}_`` prefix from on-disk basename when present."""
    match = _STORED_TS_PREFIX.match(stored_name)
    if match and match.group(2):
        return match.group(2)
    return stored_name or "upload.bin"


def build_timestamped_inbound_name(filename: str, *, now: int | None = None) -> str:
    """Return ``{unix_ts}_{sanitized_original}`` (matches outbound naming style)."""
    display = sanitize_inbound_filename(filename)
    ts = int(time.time()) if now is None else now
    return f"{ts}_{display}"


async def _unique_inbound_path(workspace: BackendWorkspace, stored_name: str) -> str:
    """Pick ``inbound/{name}``, or ``inbound/{stem}-{n}{suffix}`` on collision."""
    candidate = f"{INBOUND_DIR}/{stored_name}"
    if not await workspace.aexists(candidate):
        return candidate
    stem = Path(stored_name).stem
    suffix = Path(stored_name).suffix
    for index in range(2, 1000):
        alt = f"{INBOUND_DIR}/{stem}-{index}{suffix}"
        if not await workspace.aexists(alt):
            return alt
    raise OctopError(ErrorCode.INTERNAL_ERROR, f"cannot allocate unique path for {stored_name!r}")


async def write_inbound(
    workspace: BackendWorkspace,
    data: bytes,
    *,
    filename: str,
    media_type: str,
) -> InboundFile:
    """Persist bytes under ``inbound/{unix_ts}_{original}``."""
    validate_inbound_size(data)
    normalized_type = validate_inbound_media_type(media_type, filename)

    display_name = sanitize_inbound_filename(filename)
    if not Path(display_name).suffix:
        display_name = f"{display_name}{inbound_extension(display_name, normalized_type)}"
    stored_name = build_timestamped_inbound_name(display_name)
    path = await _unique_inbound_path(workspace, stored_name)
    await workspace.aupload_bytes(path, data)
    return InboundFile(
        path=path,
        filename=display_name,
        media_type=normalized_type,
        size=len(data),
    )


async def read_inbound_bytes(workspace: BackendWorkspace, path: str) -> bytes:
    rel = inbound_rel_path(path)
    data = await workspace.adownload_bytes(rel)
    if data is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"inbound file {rel!r} not found")
    return data


__all__ = [
    "ALLOWED_INBOUND_MEDIA_TYPES",
    "INBOUND_EXTENSION_MEDIA_TYPES",
    "InboundFile",
    "MAX_INBOUND_BYTES",
    "build_timestamped_inbound_name",
    "display_name_from_stored",
    "inbound_extension",
    "inbound_rel_path",
    "normalize_inbound_media_type",
    "read_inbound_bytes",
    "agent_facing_workspace_path",
    "resolve_inbound_attachment_path",
    "sanitize_inbound_filename",
    "validate_inbound_media_type",
    "validate_inbound_size",
    "write_inbound",
]
