"""Unit tests for storage backend probes."""

from __future__ import annotations

import json
from pathlib import Path

from octop.infra.backend.probe import probe_storage_backend
from octop.infra.db.repos.backends import BackendRow


def _row(**kwargs: object) -> BackendRow:
    base = {
        "id": 1,
        "name": "test",
        "kind": "cos",
        "endpoint": None,
        "access_key": None,
        "secret_key": None,
        "bucket": None,
        "region": None,
        "config_json": None,
        "note": None,
        "enabled": 1,
        "created_at": 0,
        "updated_at": 0,
    }
    base.update(kwargs)
    return BackendRow(**base)  # type: ignore[arg-type]


def test_object_storage_missing_fields() -> None:
    result = probe_storage_backend(_row(kind="cos"))
    assert result["ok"] is False
    assert "incomplete" in result["message"]


def test_filesystem_missing_root(tmp_path: Path) -> None:
    result = probe_storage_backend(_row(kind="filesystem", config_json="{}"))
    assert result["ok"] is False

    existing = tmp_path / "data"
    existing.mkdir()
    result = probe_storage_backend(
        _row(kind="filesystem", config_json=json.dumps({"root_dir": str(existing)})),
    )
    assert result["ok"] is True
    assert result.get("message_key") == "probe_roundtrip_ok"
