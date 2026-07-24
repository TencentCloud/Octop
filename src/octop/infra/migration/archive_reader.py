"""Read and validate a LightClaw migration export archive."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import PurePosixPath
from typing import Any

from octop.infra.migration.manifest import SUPPORTED_FORMAT_VERSION, ExportManifest

logger = logging.getLogger(__name__)

# Maximum total uncompressed size accepted (1 GB).
_MAX_TOTAL_BYTES = 1 * 1024 * 1024 * 1024
# Per-file size cap when reading individual text/JSON members (50 MB).
_MAX_MEMBER_TEXT_BYTES = 50 * 1024 * 1024


def _safe_posix(name: str) -> str:
    """Normalise a zip member name to a forward-slash posix path."""
    return name.replace("\\", "/").lstrip("/")


def _assert_no_traversal(name: str) -> None:
    """Raise ValueError if *name* contains path-traversal components."""
    parts = PurePosixPath(_safe_posix(name)).parts
    if ".." in parts:
        raise ValueError(f"Path traversal detected in archive member: {name!r}")


class ArchiveReader:
    """Thin wrapper around a ZIP archive produced by LightClaw's export endpoint.

    Usage::

        reader = ArchiveReader(zip_bytes)
        reader.validate()          # checks format, size, no traversal
        manifest = reader.manifest
        cfg = reader.read_json("config/lightclaw.json")
    """

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._zf: zipfile.ZipFile | None = None
        self._manifest: ExportManifest | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        if self._zf is not None:
            return  # already open — idempotent
        if not zipfile.is_zipfile(io.BytesIO(self._data)):
            raise ValueError("Uploaded file is not a valid zip archive")
        self._zf = zipfile.ZipFile(io.BytesIO(self._data))

    def close(self) -> None:
        if self._zf is not None:
            self._zf.close()
            self._zf = None

    def __enter__(self) -> ArchiveReader:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> ExportManifest:
        """Validate archive integrity and load the manifest.

        Returns:
            Parsed :class:`ExportManifest`.

        Raises:
            ValueError: on format mismatch, missing manifest, or path traversal.
        """
        if self._zf is None:
            self.open()
        assert self._zf is not None

        # Check for path traversal in all member names.
        total_size = 0
        for info in self._zf.infolist():
            _assert_no_traversal(info.filename)
            total_size += info.file_size
        if total_size > _MAX_TOTAL_BYTES:
            raise ValueError(
                f"Archive uncompressed size ({total_size // (1024**2)} MB) exceeds the 1 GB limit."
            )

        raw = self._read_bytes("manifest.json")
        if raw is None:
            raise ValueError("Archive is missing manifest.json")
        try:
            manifest = ExportManifest.model_validate(json.loads(raw))
        except Exception as exc:
            raise ValueError(f"Invalid manifest.json: {exc}") from exc

        if manifest.format != SUPPORTED_FORMAT_VERSION:
            raise ValueError(
                f"Unsupported export format version {manifest.format!r} "
                f"(expected {SUPPORTED_FORMAT_VERSION!r})"
            )
        if manifest.source != "lightclaw":
            raise ValueError(
                f"Unsupported export source {manifest.source!r} (expected 'lightclaw')"
            )
        self._manifest = manifest
        return manifest

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def manifest(self) -> ExportManifest:
        if self._manifest is None:
            raise RuntimeError("Call validate() first")
        return self._manifest

    def member_names(self) -> list[str]:
        assert self._zf is not None
        return [_safe_posix(info.filename) for info in self._zf.infolist()]

    def has_member(self, name: str) -> bool:
        try:
            assert self._zf is not None
            self._zf.getinfo(name)
            return True
        except KeyError:
            return False

    def _read_bytes(self, name: str) -> bytes | None:
        assert self._zf is not None
        try:
            info = self._zf.getinfo(name)
        except KeyError:
            return None
        with self._zf.open(info) as fh:
            return fh.read()

    def read_bytes(self, name: str) -> bytes | None:
        """Read a member as raw bytes. Returns None if not present."""
        return self._read_bytes(name)

    def read_text(self, name: str, *, encoding: str = "utf-8") -> str | None:
        raw = self._read_bytes(name)
        if raw is None:
            return None
        if len(raw) > _MAX_MEMBER_TEXT_BYTES:
            raise ValueError(
                f"Archive member {name!r} exceeds text read limit ({len(raw) // (1024**2)} MB)"
            )
        return raw.decode(encoding, errors="replace")

    def read_json(self, name: str) -> Any:
        """Read and parse a JSON archive member. Returns None if not present."""
        text = self.read_text(name)
        if text is None:
            return None
        return json.loads(text)

    def iter_prefix(self, prefix: str):
        """Yield (member_name, bytes) for all members whose name starts with *prefix*."""
        assert self._zf is not None
        for info in self._zf.infolist():
            safe_name = _safe_posix(info.filename)
            if safe_name.startswith(prefix) and not safe_name.endswith("/"):
                with self._zf.open(info) as fh:
                    yield safe_name, fh.read()
