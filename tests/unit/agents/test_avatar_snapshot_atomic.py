"""A published snapshot must not contain a half-written avatar."""

from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

from octop.infra.agents.experts import avatar as avatar_mod


def test_a_failed_publish_keeps_the_previous_avatar(tmp_path):
    target = tmp_path / "avatar.png"
    target.write_bytes(b"old avatar")

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(os, "replace", _boom)
    try:
        with pytest.raises(OSError):
            avatar_mod._publish_bytes_atomically(target, b"new avatar")
    finally:
        monkeypatch.undo()

    # A truncating write would have left the avatar as a prefix of the new bytes,
    # and the snapshot directory is published as a whole.
    assert target.read_bytes() == b"old avatar"
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_failed_publish_leaves_nothing_behind(tmp_path):
    target = tmp_path / "avatar.png"

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(os, "replace", _boom)
    try:
        with pytest.raises(OSError):
            avatar_mod._publish_bytes_atomically(target, b"new avatar")
    finally:
        monkeypatch.undo()

    assert list(tmp_path.iterdir()) == []


def test_the_snapshot_copy_uses_the_atomic_publish():
    source = inspect.getsource(avatar_mod)

    assert "target.write_bytes(data)" not in source
    assert "_publish_bytes_atomically(target, data)" in source
