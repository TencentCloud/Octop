"""tests/unit/test_host_paths.py"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from octop.infra.gateway.media.backend_files import is_allowed_host_temp_path


def test_is_allowed_host_temp_path_under_system_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = tmp_path / "preview.png"
    sample.write_bytes(b"png")
    if os.name == "nt":
        monkeypatch.setenv("TEMP", str(tmp_path))
        assert is_allowed_host_temp_path(sample.resolve()) is True
    else:
        assert isinstance(is_allowed_host_temp_path(sample.resolve()), bool)
