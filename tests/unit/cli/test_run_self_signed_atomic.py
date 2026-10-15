"""A failed self-signed key/cert write must not leave a partial PEM behind."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from octop.cli.commands import run as run_cmd


def test_a_failed_publish_leaves_no_partial_file(tmp_path, monkeypatch):
    key = tmp_path / "self_signed.key"

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        run_cmd._publish_bytes_atomically(key, b"-----BEGIN PRIVATE KEY-----\n")

    # A truncating write would leave this file present but unloadable, and the
    # caller only regenerates when it is missing.
    assert not key.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_successful_publish_writes_the_bytes(tmp_path):
    target = tmp_path / "self_signed.crt"

    run_cmd._publish_bytes_atomically(target, b"-----BEGIN CERTIFICATE-----\n")

    assert target.read_bytes() == b"-----BEGIN CERTIFICATE-----\n"


def test_the_generator_uses_the_atomic_publish():
    import inspect

    source = inspect.getsource(run_cmd)

    assert "key.write_bytes(" not in source
    assert "cert.write_bytes(" not in source
    assert "_publish_bytes_atomically(\n            key," in source
