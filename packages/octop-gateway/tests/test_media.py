"""Tests for octop_gateway.media (storage backend)."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop_gateway.media import FileSystemMediaBackend, MediaBackend


class TestMediaBackendABC:
    """Test that MediaBackend cannot be instantiated directly."""

    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            MediaBackend()  # type: ignore[abstract]


class TestFileSystemMediaBackend:
    """Test FileSystemMediaBackend with tmp_path fixture."""

    @pytest.mark.asyncio
    async def test_save_and_read(self, tmp_path: Path) -> None:
        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"hello world", "test.txt")
        data = await backend.read("test.txt")
        assert data == b"hello world"

    @pytest.mark.asyncio
    async def test_read_missing_raises(self, tmp_path: Path) -> None:
        backend = FileSystemMediaBackend(tmp_path)
        with pytest.raises(FileNotFoundError):
            await backend.read("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_exists_true(self, tmp_path: Path) -> None:
        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"data", "exists.bin")
        assert await backend.exists("exists.bin") is True

    @pytest.mark.asyncio
    async def test_exists_false(self, tmp_path: Path) -> None:
        backend = FileSystemMediaBackend(tmp_path)
        assert await backend.exists("nope.bin") is False

    def test_get_local_path(self, tmp_path: Path) -> None:
        backend = FileSystemMediaBackend(tmp_path)
        assert backend.get_local_path("sub/file.png") == tmp_path / "sub" / "file.png"

    def test_root_path_property(self, tmp_path: Path) -> None:
        backend = FileSystemMediaBackend(tmp_path)
        assert backend.root_path == tmp_path

    @pytest.mark.asyncio
    async def test_save_creates_subdirectories(self, tmp_path: Path) -> None:
        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"nested", "a/b/c/deep.txt")
        assert (tmp_path / "a" / "b" / "c" / "deep.txt").read_bytes() == b"nested"
