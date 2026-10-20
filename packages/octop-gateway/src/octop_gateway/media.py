"""Media storage abstraction.

Defines a pluggable backend for persisting binary media payloads. All file
I/O performed by channels (inbound persistence, outbound bytes loading)
goes through this layer, so the actual storage location (local filesystem,
object store, in-memory cache) is irrelevant to channel implementations.

Platform-specific upload/download logic lives on the channel itself:
  - inbound:  ``BaseChannel.fetch_remote_media(url)`` — platform auth GET
  - outbound: ``BaseChannel.load_media_bytes(part)`` — read backend bytes
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class MediaBackend(ABC):
    """Abstract backend for persisting media files.

    Backends are addressed by an opaque ``key`` (string). The key is also
    what gets stamped onto ``ContentPart.local_path`` for downstream readers,
    so its semantics are fully owned by the backend implementation.
    """

    @abstractmethod
    async def save(self, data: bytes, key: str) -> None:
        """Persist media data under the given key."""

    @abstractmethod
    async def read(self, key: str) -> bytes:
        """Read previously saved media data. Raises FileNotFoundError if missing."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check whether a key has been saved."""

    def get_local_path(self, key: str) -> Path | None:
        """Resolve the on-disk path for a key, when one exists.

        Filesystem-backed implementations should return the actual path so
        SDKs that demand a path (multipart upload from disk, ffmpeg input,
        etc.) can use it. Non-filesystem backends return None; callers must
        fall back to ``read(key)`` for bytes.
        """
        return None


class FileSystemMediaBackend(MediaBackend):
    """Filesystem-based media backend. Stores files at ``{root_path}/{key}``."""

    def __init__(self, root_path: Path | str = "/") -> None:
        self._root = Path(root_path)

    @property
    def root_path(self) -> Path:
        return self._root

    async def save(self, data: bytes, key: str) -> None:
        file_path = self._root / key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(data)

    async def read(self, key: str) -> bytes:
        file_path = self._root / key
        if not file_path.exists():
            raise FileNotFoundError(f"Media not found: {key}")
        return file_path.read_bytes()

    async def exists(self, key: str) -> bool:
        return (self._root / key).exists()

    def get_local_path(self, key: str) -> Path:
        return self._root / key
