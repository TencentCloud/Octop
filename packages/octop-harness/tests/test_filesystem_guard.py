"""Tests for FilesystemGuardMiddleware (execution-backend path policy)."""

from __future__ import annotations

import sys

import pytest
from deepagents.middleware.filesystem import FilesystemPermission

from octop_harness.middleware.filesystem_guard import filesystem_guard_block_reason


def test_blocks_read_on_denied_sensitive_path() -> None:
    permissions = [
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/etc/**"],
            mode="deny",
        )
    ]
    reason = filesystem_guard_block_reason(
        permissions,
        tool_name="read_file",
        params={"file_path": "/etc/passwd"},
    )
    assert reason is not None
    assert "permission denied" in reason
    assert "/etc/passwd" in reason


def test_allows_read_outside_denied_prefix() -> None:
    permissions = [
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/etc/**"],
            mode="deny",
        )
    ]
    assert (
        filesystem_guard_block_reason(
            permissions,
            tool_name="read_file",
            params={"file_path": "/workspace/SOUL.md"},
        )
        is None
    )


def test_blocks_write_file_tool() -> None:
    permissions = [
        FilesystemPermission(
            operations=["write"],
            paths=["/**/.env"],
            mode="deny",
        )
    ]
    reason = filesystem_guard_block_reason(
        permissions,
        tool_name="write_file",
        params={"file_path": "/home/user/project/.env"},
    )
    assert reason is not None
    assert "write" in reason


def test_blocks_ls_on_denied_directory_root() -> None:
    """``/etc/**`` must also deny listing the directory itself (``ls /etc``)."""
    permissions = [
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/etc/**"],
            mode="deny",
        )
    ]
    reason = filesystem_guard_block_reason(
        permissions,
        tool_name="ls",
        params={"path": "/etc"},
    )
    assert reason is not None
    assert "permission denied" in reason


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS /etc → /private/etc alias")
def test_blocks_ls_on_macos_private_etc_alias() -> None:
    """macOS ``/etc`` → ``/private/etc``; deny rules must cover the real path."""
    permissions = [
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/etc/**"],
            mode="deny",
        )
    ]
    reason = filesystem_guard_block_reason(
        permissions,
        tool_name="ls",
        params={"path": "/private/etc"},
    )
    assert reason is not None
    assert "permission denied" in reason
