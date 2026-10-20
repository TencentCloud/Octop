"""Shared base class for cloud object storage backends (OSS, OBS, …).

All providers store files as JSON-enveloped ``FileData`` objects under a
configurable key prefix. The public ``BackendProtocol`` methods (read, write,
edit, ls, glob, grep, …) are identical across providers; only the SDK calls
differ. Subclasses implement a small set of abstract primitives and inherit
everything else from here.

Storage layout
--------------
Every virtual file at ``/foo/bar.txt`` maps to an object whose key is
``<prefix>foo/bar.txt``. The object body is JSON matching deepagents'
``FileData`` shape::

    {"content": "...", "encoding": "utf-8",
     "created_at": "...", "modified_at": "..."}
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileData,
    FileInfo,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from deepagents.backends.utils import (
    create_file_data,
    file_data_to_string,
    grep_matches_from_files,
    perform_string_replacement,
    slice_read_response,
    update_file_data,
)
from wcmatch import glob as wcglob

from octop_harness.backends.storage_errors import format_storage_error, wrap_io_error
from octop_harness.backends.utils import relative_virtual_path

logger = logging.getLogger(__name__)

_BASE_STORAGE_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    json.JSONDecodeError,
    UnicodeDecodeError,
)


def _finalize_ls_entries(path: str, entries: list[FileInfo]) -> list[FileInfo]:
    """Single-level listing: one node per path, never the directory being listed.

    Object stores emit both a trailing-slash marker and a CommonPrefix for the
    same folder. The workspace tree treats those as one directory.
    """
    listed = path.replace("\\", "/").rstrip("/") or "/"
    merged: dict[str, FileInfo] = {}
    for entry in entries:
        raw = str(entry.get("path") or "").replace("\\", "/").strip()
        if not raw or raw in {".", "./"}:
            continue
        is_dir = bool(entry.get("is_dir")) or raw.endswith("/")
        norm = raw.rstrip("/") or "/"
        if norm in {".", "./", listed}:
            continue
        existing = merged.get(norm)
        if existing is not None:
            if is_dir and not existing.get("is_dir"):
                merged[norm] = {**entry, "path": norm, "is_dir": True}
            continue
        merged[norm] = {**entry, "path": norm, "is_dir": is_dir}
    return sorted(merged.values(), key=lambda item: (not item.get("is_dir"), str(item.get("path") or "")))


class CloudStorageBackend(BackendProtocol, ABC):
    """Abstract base for cloud object storage backends.

    Subclasses must provide:
    - ``_prefix`` property: the stripped key prefix string
    - ``_get_file_data(path)`` → ``FileData | None``
    - ``_put_file_data(path, file_data)``
    - ``_ls_entries(path)`` → ``list[FileInfo]``  (single-level listing)
    - ``_collect_recursive(path)`` → ``dict[str, FileData]``
    - ``_iter_prefix_object_keys(path)`` → iterable of raw object keys
    - ``_prefix_has_objects(path)`` → ``bool``
    - ``_copy_object(src_virtual, dest_virtual)``
    - ``_put_dir_marker(virtual_dir)``
    - ``delete_object(path)``  (public, used by probe)
    - ``delete_prefix(path)`` → ``int``
    """

    def _storage_error_types(self) -> tuple[type[BaseException], ...]:
        """Exception types that SDK primitives may raise into public methods."""
        return _BASE_STORAGE_ERRORS

    # ------------------------------------------------------------------
    # Path / key plumbing  (shared; subclass sets self._key_prefix)
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def _prefix(self) -> str:
        """Stripped key prefix (no leading/trailing slashes)."""

    def _key(self, path: str) -> str:
        """Map a virtual absolute path to a storage key."""
        clean = path.lstrip("/")
        if self._prefix:
            return f"{self._prefix}/{clean}" if clean else self._prefix + "/"
        return clean

    def _virtual_path(self, key: str) -> str:
        """Inverse of ``_key``."""
        if self._prefix and key.startswith(self._prefix + "/"):
            key = key[len(self._prefix) + 1 :]
        elif self._prefix and key == self._prefix:
            return "/"
        return "/" + key.lstrip("/")

    def _virtual(self, path: str) -> str:
        return path if path.startswith("/") else f"/{path}"

    def _prefix_key(self, path: str) -> str:
        pk = self._key(self._virtual(path).rstrip("/"))
        if pk and not pk.endswith("/"):
            pk = f"{pk}/"
        return pk

    # ------------------------------------------------------------------
    # Subclass primitives (SDK-specific)
    # ------------------------------------------------------------------

    @abstractmethod
    def _get_file_data(self, path: str) -> FileData | None:
        """Return ``FileData`` for ``path``, or ``None`` if missing."""

    @abstractmethod
    def _put_file_data(self, path: str, file_data: FileData) -> None:
        """Persist ``file_data`` at ``path``."""

    @abstractmethod
    def _ls_entries(self, path: str) -> list[FileInfo]:
        """Single-level listing under ``path``."""

    @abstractmethod
    def _collect_recursive(self, path: str) -> dict[str, FileData]:
        """Return every file under ``path`` with its ``FileData``."""

    @abstractmethod
    def _iter_prefix_object_keys(self, path: str) -> Any:
        """Yield raw storage keys for all objects under ``path``."""

    @abstractmethod
    def _prefix_has_objects(self, path: str) -> bool:
        """Return ``True`` when at least one object exists under ``path``."""

    @abstractmethod
    def _copy_object(self, src: str, dest: str) -> None:
        """Server-side copy of the object at virtual path ``src`` to ``dest``."""

    @abstractmethod
    def _put_dir_marker(self, virtual_dir: str) -> None:
        """Create the empty trailing-slash object that represents *virtual_dir*."""

    @abstractmethod
    def delete_object(self, path: str) -> None:
        """Delete the storage object backing virtual ``path``."""

    @abstractmethod
    def delete_prefix(self, path: str) -> int:
        """Delete every object under ``path``; return count removed."""

    # ------------------------------------------------------------------
    # JSON envelope helpers (shared)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_body(raw: bytes | str) -> FileData:
        """Decode a stored object body into ``FileData``.

        Workspace objects are JSON envelopes. Existing S3-compatible buckets
        may hold raw text or binary; those are accepted without requiring
        the envelope.
        """
        if isinstance(raw, bytes):
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                return CloudStorageBackend._bytes_to_file_data(raw)
            raw = text
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return create_file_data(raw)
        if isinstance(data, dict) and "content" in data and "encoding" in data:
            return data  # type: ignore[return-value]
        return create_file_data(raw)

    @staticmethod
    def _encode_file_data(file_data: FileData) -> bytes:
        return json.dumps(file_data, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _bytes_to_file_data(raw: bytes) -> FileData:
        try:
            return create_file_data(raw.decode("utf-8"), encoding="utf-8")
        except UnicodeDecodeError:
            encoded = base64.standard_b64encode(raw).decode("ascii")
            return create_file_data(encoded, encoding="base64")

    @staticmethod
    def _file_data_to_bytes(file_data: FileData) -> bytes:
        content = file_data.get("content") or ""
        encoding = str(file_data.get("encoding") or "utf-8").lower()
        if encoding == "base64":
            return base64.standard_b64decode(str(content))
        return str(content).encode("utf-8")

    # ------------------------------------------------------------------
    # BackendProtocol — read
    # ------------------------------------------------------------------

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        try:
            file_data = self._get_file_data(file_path)
        except self._storage_error_types() as exc:
            return ReadResult(error=wrap_io_error("reading", file_path, exc))
        if file_data is None:
            return ReadResult(error=f"Error: File '{file_path}' not found")
        sliced = slice_read_response(file_data, offset, limit)
        return sliced if isinstance(sliced, ReadResult) else ReadResult(file_data=sliced)

    # ------------------------------------------------------------------
    # BackendProtocol — write (create-only)
    # ------------------------------------------------------------------

    def write(self, file_path: str, content: str) -> WriteResult:
        try:
            existing = self._get_file_data(file_path)
        except self._storage_error_types() as exc:
            return WriteResult(error=wrap_io_error("checking", file_path, exc), path=None)
        if existing is not None:
            return WriteResult(
                error=(
                    f"Cannot write to {file_path} because it already exists. "
                    "Read and then make an edit, or write to a new path."
                ),
                path=None,
            )
        try:
            self._put_file_data(file_path, create_file_data(content))
        except self._storage_error_types() as exc:
            return WriteResult(error=wrap_io_error("writing", file_path, exc), path=None)
        return WriteResult(error=None, path=file_path)

    # ------------------------------------------------------------------
    # BackendProtocol — edit (string replacement)
    # ------------------------------------------------------------------

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        try:
            file_data = self._get_file_data(file_path)
        except self._storage_error_types() as exc:
            return EditResult(error=wrap_io_error("reading", file_path, exc), path=None, occurrences=None)
        if file_data is None:
            return EditResult(error=f"Error: File '{file_path}' not found", path=None, occurrences=None)

        original_content = file_data_to_string(file_data)
        replacement = perform_string_replacement(original_content, old_string, new_string, replace_all=replace_all)
        if isinstance(replacement, str):
            return EditResult(error=replacement, path=None, occurrences=None)
        new_content, occurrences = replacement

        try:
            self._put_file_data(file_path, update_file_data(file_data, new_content))
        except self._storage_error_types() as exc:
            return EditResult(error=wrap_io_error("writing", file_path, exc), path=None, occurrences=None)
        return EditResult(error=None, path=file_path, occurrences=occurrences)

    # ------------------------------------------------------------------
    # BackendProtocol — ls
    # ------------------------------------------------------------------

    def ls(self, path: str) -> LsResult:
        try:
            entries = self._ls_entries(path)
        except self._storage_error_types() as exc:
            return LsResult(error=wrap_io_error("listing", path, exc))
        return LsResult(entries=_finalize_ls_entries(path, entries))

    def ls_info(self, path: str) -> list[FileInfo]:
        return self.ls(path).entries or []

    # ------------------------------------------------------------------
    # BackendProtocol — glob & grep
    # ------------------------------------------------------------------

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        search_path = path if path is not None else "/"
        try:
            files = self._collect_recursive(search_path)
            flags = wcglob.BRACE | wcglob.GLOBSTAR | wcglob.DOTGLOB
            base = search_path.rstrip("/") or "/"
            matched: list[FileInfo] = []
            for fp in sorted(files):
                rel = fp[len(base) + 1 :] if fp.startswith(base + "/") else fp.lstrip("/")
                if wcglob.globmatch(fp, pattern, flags=flags) or wcglob.globmatch(rel, pattern, flags=flags):
                    matched.append({"path": fp, "is_dir": False})
        except self._storage_error_types() as exc:
            return GlobResult(error=f"Error during glob: {format_storage_error(exc)}")
        return GlobResult(matches=matched)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        return self.glob(pattern, path=path).matches or []

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        del max_count
        try:
            files = self._collect_recursive(path or "/")
        except self._storage_error_types() as exc:
            return GrepResult(error=f"Error listing files: {format_storage_error(exc)}")
        return grep_matches_from_files(files, pattern=pattern, path=path, glob=glob)

    def grep_raw(self, pattern: str, path: str | None = None, glob: str | None = None) -> list[GrepMatch] | str:
        result = self.grep(pattern, path=path, glob=glob)
        if result.error:
            return result.error
        return result.matches or []

    # ------------------------------------------------------------------
    # download_files / upload_files
    # ------------------------------------------------------------------

    def download_files(self, paths: list[str]) -> list[Any]:
        from deepagents.backends.protocol import FileDownloadResponse

        results: list[Any] = []
        for path in paths:
            try:
                file_data = self._get_file_data(path)
            except self._storage_error_types() as exc:
                logger.warning("download_files error for %s: %s", path, exc)
                results.append(FileDownloadResponse(error="invalid_path", path=path, content=None))
                continue
            if file_data is None:
                results.append(FileDownloadResponse(error="file_not_found", path=path, content=None))
                continue
            results.append(
                FileDownloadResponse(
                    path=path,
                    content=self._file_data_to_bytes(file_data),
                    error=None,
                )
            )
        return results

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[Any]:
        from deepagents.backends.protocol import FileUploadResponse

        results: list[Any] = []
        for path, raw in files:
            try:
                blob = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
                self._put_file_data(path, self._bytes_to_file_data(blob))
                results.append(FileUploadResponse(path=path, error=None))
            except self._storage_error_types() as exc:
                logger.warning("upload_files error for %s: %s", path, exc)
                results.append(FileUploadResponse(path=path, error="invalid_path"))
        return results

    # ------------------------------------------------------------------
    # delete_path / move_path (shared tree operations)
    # ------------------------------------------------------------------

    def delete_path(self, path: str) -> None:
        virtual = self._virtual(path)
        if self._get_file_data(virtual) is not None:
            self.delete_object(virtual)
            return
        deleted = self.delete_prefix(virtual)
        if deleted == 0:
            raise FileNotFoundError(f"cannot delete {path!r}: not found")

    def mkdir_path(self, path: str) -> None:
        """Create directory prefixes (empty objects with a trailing slash)."""
        virtual = self._virtual(path).rstrip("/")
        if virtual in ("", "/"):
            return
        parts = [part for part in virtual.split("/") if part]
        acc: list[str] = []
        for part in parts:
            acc.append(part)
            current = "/" + "/".join(acc)
            if self._get_file_data(current) is not None:
                raise FileExistsError(f"cannot mkdir {path!r}: file exists")
            self._put_dir_marker(current)

    def move_path(self, src: str, dest: str) -> None:
        src_v = self._virtual(src)
        dest_v = self._virtual(dest)
        if src_v == dest_v:
            return
        if dest_v.startswith(f"{src_v.rstrip('/')}/"):
            raise ValueError(f"cannot move {src!r} into its own descendant")
        if self._get_file_data(dest_v) is not None or self._prefix_has_objects(dest_v):
            raise FileExistsError(f"destination already exists: {dest!r}")

        if self._get_file_data(src_v) is not None:
            self._copy_object(src_v, dest_v)
            self.delete_object(src_v)
            return

        moved = self._move_prefix(src_v, dest_v)
        if moved == 0:
            raise FileNotFoundError(f"cannot move {src!r}: not found")

    def _move_prefix(self, src: str, dest: str) -> int:
        src_root = self._virtual(src).rstrip("/")
        dest_root = self._virtual(dest).rstrip("/")
        moved = 0
        for key in self._iter_prefix_object_keys(src):
            virtual_src = self._virtual_path(str(key))
            rel = relative_virtual_path(virtual_src, src_root)
            if rel is None:
                continue
            dest_virtual = f"{dest_root}/{rel}" if rel else dest_root
            self._copy_object(virtual_src, dest_virtual)
            self.delete_object(virtual_src)
            moved += 1
        return moved

    # ------------------------------------------------------------------
    # Async wrappers (run sync work in a thread)
    # ------------------------------------------------------------------

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return await _to_thread(self.read, file_path, offset, limit)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return await _to_thread(self.write, file_path, content)

    async def aedit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        return await _to_thread(self.edit, file_path, old_string, new_string, replace_all)

    async def als(self, path: str) -> LsResult:
        return await _to_thread(self.ls, path)

    async def als_info(self, path: str) -> list[FileInfo]:
        return await _to_thread(self.ls_info, path)

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        return await _to_thread(self.glob, pattern, path)

    async def aglob_info(self, pattern: str, path: str | None = None) -> list[FileInfo]:
        return await _to_thread(self.glob_info, pattern, path)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        return await _to_thread(lambda: self.grep(pattern, path, glob, max_count=max_count))

    async def agrep_raw(self, pattern: str, path: str | None = None, glob: str | None = None) -> list[GrepMatch] | str:
        return await _to_thread(self.grep_raw, pattern, path, glob)

    async def adownload_files(self, paths: list[str]) -> list[Any]:
        return await _to_thread(self.download_files, paths)

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[Any]:
        return await _to_thread(self.upload_files, files)

    async def adelete_object(self, path: str) -> None:
        await _to_thread(self.delete_object, path)

    async def adelete_path(self, path: str) -> None:
        await _to_thread(self.delete_path, path)

    async def amove_path(self, src: str, dest: str) -> None:
        await _to_thread(self.move_path, src, dest)

    async def adelete_prefix(self, path: str) -> int:
        return await _to_thread(self.delete_prefix, path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _to_thread[T](fn: Callable[..., T], *args: Any) -> T:
    """Run a sync callable in the default thread executor."""
    return await asyncio.to_thread(fn, *args)


__all__ = ["CloudStorageBackend"]
