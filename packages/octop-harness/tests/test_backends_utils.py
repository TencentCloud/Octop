"""Tests for ``octop_harness.backends.utils``."""

from __future__ import annotations

from pathlib import Path

import pytest
from deepagents.backends import FilesystemBackend

from octop_harness.backends.utils import (
    anchor_at_backend_root,
    backend_file_exists,
    backend_write_force,
    is_complete_storage_path,
    materialize_storage_path,
)


@pytest.fixture
def backend(tmp_path: Path) -> FilesystemBackend:
    return FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)


class TestBackendWriteForce:
    def test_creates_new_file(self, backend: FilesystemBackend) -> None:
        backend_write_force(backend, "/hello.txt", "world")
        result = backend.read("/hello.txt")
        assert result.file_data["content"] == "world"

    def test_overwrites_existing_file(self, backend: FilesystemBackend) -> None:
        backend_write_force(backend, "/a.txt", "v1")
        backend_write_force(backend, "/a.txt", "v2")
        result = backend.read("/a.txt")
        assert result.file_data["content"] == "v2"

    def test_no_op_when_content_unchanged(self, backend: FilesystemBackend) -> None:
        backend_write_force(backend, "/a.txt", "same")
        backend_write_force(backend, "/a.txt", "same")
        result = backend.read("/a.txt")
        assert result.file_data["content"] == "same"


class TestBackendFileExists:
    def test_returns_false_for_missing(self, backend: FilesystemBackend) -> None:
        assert backend_file_exists(backend, "/nope.txt") is False

    def test_returns_true_for_existing(self, backend: FilesystemBackend) -> None:
        backend_write_force(backend, "/yes.txt", "hi")
        assert backend_file_exists(backend, "/yes.txt") is True


class TestIsCompleteStoragePath:
    def test_tilde_path(self) -> None:
        assert is_complete_storage_path("~/.octop/agents/alice/SOUL.md")

    def test_root_anchored_virtual_path(self) -> None:
        assert not is_complete_storage_path("/SOUL.md")

    def test_fragment(self) -> None:
        assert not is_complete_storage_path("SOUL.md")


class TestAnchorAtBackendRoot:
    def test_fragment(self) -> None:
        assert anchor_at_backend_root("SOUL.md") == "/SOUL.md"

    def test_dot_fragment(self) -> None:
        assert anchor_at_backend_root("./AGENTS.md") == "/AGENTS.md"

    def test_hidden_fragment(self) -> None:
        assert anchor_at_backend_root(".bootstrapped") == "/.bootstrapped"

    def test_root_relative_absolute(self) -> None:
        assert anchor_at_backend_root("/skills/foo") == "/skills/foo"

    def test_complete_tilde_path_unchanged(self) -> None:
        path = "~/.octop/agents/alice/SOUL.md"
        assert anchor_at_backend_root(path) == path

    def test_already_anchored_unchanged(self) -> None:
        assert anchor_at_backend_root("/SOUL.md") == "/SOUL.md"


class TestMaterializeStoragePath:
    def test_host_mount_root_relative(self, tmp_path: Path) -> None:
        target = tmp_path / "SOUL.md"
        target.write_text("x", encoding="utf-8")
        assert materialize_storage_path("/SOUL.md", host_mount=tmp_path) == target

    def test_backend_mount(self, tmp_path: Path) -> None:
        backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
        target = tmp_path / "chart.png"
        target.write_bytes(b"png")
        assert materialize_storage_path("/chart.png", backend=backend) == target

    def test_must_exist_false_when_missing(self, tmp_path: Path) -> None:
        backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
        assert materialize_storage_path("/missing.png", backend=backend, must_exist=True) is None
