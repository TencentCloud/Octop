"""Tests for octop_harness.backends.probe."""

from __future__ import annotations

from pathlib import Path

from octop_harness.backends.probe import probe_backend


def test_probe_filesystem_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    result = probe_backend(
        {"type": "filesystem", "root_dir": str(root), "virtual_mode": True},
    )
    assert result["ok"] is True
    assert result.get("message_key") == "probe_roundtrip_ok"


def test_probe_incomplete_cos() -> None:
    result = probe_backend({"type": "cos", "bucket": "only-bucket"})
    assert result["ok"] is False


def test_probe_postgres_missing_host() -> None:
    result = probe_backend({"type": "postgres"})
    assert result["ok"] is False
