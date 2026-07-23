"""Migrate uploaded files from LightClaw export archive into an Octop agent workspace.

LightClaw stores uploads at ``WORKING_DIR/uploads/{uuid}{ext}`` with
sidecar metadata in ``uploads/.meta/{uuid}{ext}.json``.

Octop stores inbound attachments under ``inbound/`` inside each agent's
workspace directory.  Files are written directly to disk (the agent is not
running during import, so we bypass BackendWorkspace to avoid path-resolution
issues on macOS where ``/tmp`` resolves to ``/private/tmp``).
"""

from __future__ import annotations

import logging
import mimetypes
import time
from pathlib import Path
from typing import Any

from octop.infra.gateway.media.inbound_store import (
    build_timestamped_inbound_name,
    sanitize_inbound_filename,
    validate_inbound_media_type,
)
from octop.infra.migration.archive_reader import ArchiveReader
from octop.infra.migration.report import MigrationReport

logger = logging.getLogger(__name__)

# Maximum individual file size accepted during upload migration (20 MB — matches inbound_store).
_MAX_FILE_BYTES = 20 * 1024 * 1024

_ALLOWED_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".txt",
        ".md",
        ".csv",
        ".json",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".svg",
        ".mp3",
        ".mp4",
        ".wav",
        ".ogg",
        ".zip",
        ".tar",
        ".gz",
    }
)


def _guess_media_type(filename: str) -> str:
    mt, _ = mimetypes.guess_type(filename)
    return mt or "application/octet-stream"


def _load_meta(reader: ArchiveReader, file_id: str) -> dict[str, Any]:
    """Load sidecar metadata for a file_id if present."""
    meta_raw = reader.read_json(f"uploads/.meta/{file_id}.json")
    if isinstance(meta_raw, dict):
        return meta_raw
    return {}


async def migrate_uploads(
    reader: ArchiveReader,
    workspace_dir: Path,
    report: MigrationReport,
) -> None:
    """Write all upload files from *reader* into ``workspace_dir/inbound/``.

    Files are written directly to disk rather than through BackendWorkspace to
    avoid path-resolution bugs (e.g. macOS ``/tmp`` → ``/private/tmp`` symlink
    causing the resolved absolute path to be written *inside* workspace_dir as
    a mirrored host subtree).
    """
    inbound_dir = workspace_dir / "inbound"
    inbound_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0

    for member_name, raw_bytes in reader.iter_prefix("uploads/"):
        # Skip .meta sidecar files (they're metadata, not actual files)
        if "/.meta/" in member_name or "/.derived/" in member_name:
            continue

        # Derive the file_id (basename without leading path)
        file_id = member_name[len("uploads/") :]
        if not file_id or "/" in file_id:
            # nested paths (other than .meta) are unexpected; skip
            skipped += 1
            continue

        if len(raw_bytes) > _MAX_FILE_BYTES:
            report.warn(f"Skipping large upload {file_id!r} ({len(raw_bytes) // 1024} KB)")
            skipped += 1
            continue

        # Load sidecar meta for original filename
        meta = _load_meta(reader, file_id)
        original_filename = str(meta.get("filename") or file_id)
        media_type = str(meta.get("media_type") or _guess_media_type(original_filename))

        # Validate extension
        ext = Path(original_filename).suffix.lower()
        if ext and ext not in _ALLOWED_EXTENSIONS:
            report.warn(
                f"Skipping upload with unsupported extension {ext!r}: {original_filename!r}"
            )
            skipped += 1
            continue

        try:
            # Normalise media type (silently fall back to octet-stream for unknown types)
            try:
                media_type = validate_inbound_media_type(media_type)
            except Exception:
                media_type = "application/octet-stream"

            display_name = sanitize_inbound_filename(original_filename)
            stored_name = build_timestamped_inbound_name(
                display_name, now=int(meta.get("created_at") or time.time())
            )
            dest = inbound_dir / stored_name
            dest.write_bytes(raw_bytes)
            written += 1
        except Exception:
            logger.exception("Failed to migrate upload %s", file_id)
            report.warn(f"Failed to write upload {file_id!r} to workspace")
            skipped += 1

    report.uploads_written = written
    report.uploads_skipped = skipped
    logger.info("Uploads migrated: %d written, %d skipped", written, skipped)
